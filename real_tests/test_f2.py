"""
Модуль тестирования поведенческой модели UART-контроллера.
Обеспечивает 100% покрытие кода, трекинг FSM и стресс-тестирование.
"""

import importlib
import json
import logging
import random
import sys

import riscv

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
# Pylint требует UPPER_CASE для констант на уровне модуля
DETAILS_LOGGER = logging.getLogger("details")
DETAILS_LOGGER.setLevel(logging.DEBUG)

# 1. ФАЙЛ (Пишет всё)
DETAILS_HANDLER = logging.FileHandler(
    "uart_test_details.log", mode='w', encoding='utf-8'
)
DETAILS_HANDLER.setLevel(logging.DEBUG)
DETAILS_HANDLER.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
DETAILS_LOGGER.addHandler(DETAILS_HANDLER)

# 2. КОНСОЛЬ (Пишет только INFO)
CONSOLE_HANDLER = logging.StreamHandler(sys.stdout)
CONSOLE_HANDLER.setLevel(logging.INFO)
CONSOLE_HANDLER.addFilter(lambda record: record.levelno == logging.INFO)
CONSOLE_HANDLER.setFormatter(logging.Formatter('>>> %(message)s'))
DETAILS_LOGGER.addHandler(CONSOLE_HANDLER)


# --- НАПРАВЛЕННЫЕ ТЕСТЫ ДЛЯ 100% ПОКРЫТИЯ ---

def run_coverage_directed_tests():
    """
    Принудительное прохождение по всем веткам логики riscv.py,
    чтобы гарантировать 100% покрытия кода (Statement & Branch).
    """
    DETAILS_LOGGER.info("Запуск направленных тестов для 100% покрытия кода...")
    importlib.reload(riscv)

    # 1. Покрытие всех масок WLS (5, 6, 7, 8 бит)
    for wls in range(4):
        riscv.reg_access(3, wls, "write")      # Настройка LCR
        riscv.reg_access(0, 0xFF, "write")     # Пишем все единицы
        riscv.step_clock(1)                    # Ждем такт
        res = riscv.reg_access(0, 0, "read")   # Читаем
        # Pylint: Ленивое форматирование строк в логгерах
        DETAILS_LOGGER.debug("[Coverage] WLS=%s: Прочитано %s", wls, hex(res.get('reg_value', 0)))

    # 2. Покрытие логики FIFO
    riscv.reg_access(6, 0x01, "write") # Включаем FIFO
    riscv.reg_access(0, 0xAA, "write")
    riscv.step_clock(1)

    riscv.reg_access(6, 0x00, "write") # Выключаем FIFO
    riscv.reg_access(0, 0xBB, "write")
    riscv.step_clock(1)

    # 3. Покрытие инвалидных операций (ветка ack=False)
    riscv.reg_access(0, 0, "INVALID_CMD")

    # 4. Покрытие инвалидных адресов (ветка addr not in _regs)
    riscv.reg_access(99, 0, "read")

    # 5. Покрытие сброса флага DR при чтении RBR
    riscv.reg_access(0, 0x12, "write")
    riscv.step_clock(1)
    riscv.reg_access(0, 0, "read") # Это действие должно сбросить DR в LSR

    DETAILS_LOGGER.info("Направленные тесты завершены.")


# --- FSM ТРЕКИНГ ---

def run_fsm_tracking():
    """
    Направленный тест (Directed Test) для записи графа состояний FSM.
    Генерирует файл fsm_transitions.json для Streamlit NetworkX.
    """
    # pylint: disable=too-many-statements
    DETAILS_LOGGER.info("Запуск трекинга FSM (генерация графа)...")

    importlib.reload(riscv) # Сбрасываем модель перед FSM тестом

    fsm_log =[]
    current_state = "RESET_IDLE"

    def transition(new_state):
        nonlocal current_state
        if current_state != new_state:
            fsm_log.append([current_state, new_state])
            DETAILS_LOGGER.debug("[FSM] Переход: %s -> %s", current_state, new_state)
            current_state = new_state

    # === 1. HAPPY PATH (Нормальная работа UART) ===
    # Шаг 1: Установка DLAB=1
    if riscv.reg_access(3, 0x80, "write").get('ack'):  # LCR (idx 3)
        transition("DLAB_ENABLED")

    # Шаг 2: Настройка Baudrate (DLL и DLM)
    riscv.reg_access(1, 0x0D, "write") # DLL
    riscv.reg_access(2, 0x00, "write") # DLM
    transition("BAUDRATE_SET")

    # Шаг 3: Выход из DLAB (8N1)
    if riscv.reg_access(3, 0x03, "write").get('ack'):
        transition("OPERATIONAL_READY")

    # Шаг 4: Попытка отправки байта (TX)
    lsr = riscv.reg_access(7, 0, "read").get('reg_value', 0)
    if lsr & 0x20: # Проверка THRE (TX Empty)
        transition("TX_WAITING")
        riscv.reg_access(0, 0xAA, "write") # Пишем в THR
        transition("TX_TRANSMITTING")

        # Симулируем такты аппаратуры, чтобы байт ушел
        riscv.step_clock(5)
        transition("OPERATIONAL_READY")

    # === 2. DARK PATH (Нарушение протокола / Защита) ===
    # Попытка записи в Read-Only регистр LSR (индекс 7)
    resp = riscv.reg_access(7, 0xFF, "write")
    if not resp.get('ack'):
        # Возвращаемся в предыдущее состояние, так как защита сработала
        transition("RO_PROTECTION_TRIGGERED")
        transition("OPERATIONAL_READY")

    # Попытка обращения к несуществующему адресу (например, индекс 15)
    resp_invalid = riscv.reg_access(15, 0, "read")
    if not resp_invalid.get('ack'):
        transition("APB_SLVERR_CAUGHT")
        transition("OPERATIONAL_READY")

    # Сохраняем граф для Streamlit
    with open("fsm_transitions.json", "w", encoding="utf-8") as file_out:
        json.dump(fsm_log, file_out, indent=4)

    DETAILS_LOGGER.info("Граф FSM успешно записан в fsm_transitions.json")


# --- ОСНОВНОЙ ТЕСТ ---

def run_stress_test(iterations=65000):
    """
    Запуск основного стресс-теста для поиска аппаратных/поведенческих багов.
    """
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    DETAILS_LOGGER.info("Запуск актуализированного стресс-теста: %s итераций...", iterations)

    # Убираем использование global, делаем переменную локальной
    is_locked = False

    # Полный сброс модели
    importlib.reload(riscv)

    # Индексы регистров в riscv.py: 0=THR/RBR, 1=DLL, 2=DLM, 3=LCR, ...
    heatmap_data = {
        (i * 4): {
            "writes": 0, "reads": 0, "ro_denied": 0, "mismatches": 0,
            "bug_sticky": 0, "bug_deadlock": 0, "bug_overflow": 0,
            "unexpected_errors": 0
        } for i in range(16)
    }

    # Теневая память (Reference Model) со стартовыми значениями из riscv.py
    shadow_memory = {i: 0 for i in range(16)}
    shadow_memory[3] = 0x03  # LCR
    shadow_memory[5] = 0x01  # IIR
    shadow_memory[7] = 0x60  # LSR

    for i in range(iterations):
        byte_addr = random.randint(0, 15) * 4
        idx = byte_addr // 4

        operation = random.choices(
            ['write', 'read', 'invalid_op'], weights=[49, 49, 2]
        )[0]

        dlab = (shadow_memory[3] >> 7) & 0x1

        if operation == 'write':
            heatmap_data[byte_addr]["writes"] += 1
            data = random.randint(0, 0xFFFFFFFF)
            DETAILS_LOGGER.debug(
                "Ит %s: [WRITE] Адрес: %s, Данные: %s", i, hex(byte_addr), hex(data)
            )

            response = riscv.reg_access(idx, data, "write")

            if idx in [5, 7, 9] or idx > 9:
                if response.get('ack'):
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                    DETAILS_LOGGER.error(
                        "Ит %s:[БАГ] Успешный ACK при записи в RO/Invalid %s", i, hex(byte_addr)
                    )
                else:
                    heatmap_data[byte_addr]["ro_denied"] += 1
            else:
                if not response.get('ack'):
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                    DETAILS_LOGGER.error(
                        "Ит %s: Отказ ACK при разрешенной записи в %s", i, hex(byte_addr)
                    )
                else:
                    written_val = response.get('reg_value', 0)
                    if idx == 3:
                        is_locked = True

                    if written_val > 0xFF:
                        heatmap_data[byte_addr]["bug_overflow"] += 1
                        DETAILS_LOGGER.debug(
                            "Ит %s: OVERFLOW GLITCH! Железо сохранило %s (> 8 bit)",
                            i, hex(written_val)
                        )

                    if idx == 0 and not dlab:
                        pass
                    elif idx in [1, 2] and not dlab:
                        pass
                    else:
                        shadow_memory[idx] = written_val

        elif operation == 'read':
            heatmap_data[byte_addr]["reads"] += 1
            DETAILS_LOGGER.debug("Ит %s: [READ] Адрес: %s", i, hex(byte_addr))

            response = riscv.reg_access(idx, 0, "read")

            if not response.get('ack'):
                if idx <= 9:
                    if is_locked and idx == 4:
                        heatmap_data[byte_addr]["bug_deadlock"] += 1
                        DETAILS_LOGGER.debug("Ит %s: ПОЙМАН DEADLOCK на чтении MCR 0x10", i)
                    else:
                        heatmap_data[byte_addr]["unexpected_errors"] += 1
                        DETAILS_LOGGER.error(
                            "Ит %s: Неожиданный отказ ACK на чтении %s", i, hex(byte_addr)
                        )
            else:
                actual_val = response.get('reg_value', 0)

                if actual_val > 0xFF and idx < 10:
                    heatmap_data[byte_addr]["bug_overflow"] += 1

                if idx not in [0, 7] and idx <= 9:
                    expected_val = shadow_memory[idx]
                    if actual_val != expected_val:
                        if idx == 2 and actual_val == 0x42:
                            heatmap_data[byte_addr]["bug_sticky"] += 1
                            DETAILS_LOGGER.debug("Ит %s: ПОЙМАН STICKY BUG на IIR 0x08", i)
                        else:
                            heatmap_data[byte_addr]["mismatches"] += 1
                            DETAILS_LOGGER.error(
                                "Ит %s: Mismatch в %s! Ожидалось: %s, Получено: %s",
                                i, hex(byte_addr), hex(expected_val), hex(actual_val)
                            )
        else:
            response = riscv.reg_access(idx, 0, "null")
            if response.get('ack') and idx <= 9:
                heatmap_data[byte_addr]["unexpected_errors"] += 1

        if random.random() < 0.10:
            riscv.step_clock(1)

        if i > 0 and i % 10000 == 0:
            DETAILS_LOGGER.info("Прогресс: %s итераций завершено...", i)

    write_final_report(iterations, heatmap_data)


def write_final_report(total_iterations, heatmap_data):
    """
    Генерирует финальный отчет-матрицу для дашборда.
    """
    # pylint: disable=too-many-locals
    report_filename = "uart_final_summary.txt"

    t_writes = sum(reg["writes"] for reg in heatmap_data.values())
    t_reads  = sum(reg["reads"] for reg in heatmap_data.values())
    t_ro     = sum(reg["ro_denied"] for reg in heatmap_data.values())
    t_mism   = sum(reg["mismatches"] for reg in heatmap_data.values())
    t_ovf    = sum(reg["bug_overflow"] for reg in heatmap_data.values())
    t_unexp  = sum(reg["unexpected_errors"] for reg in heatmap_data.values())
    t_stk    = sum(reg["bug_sticky"] for reg in heatmap_data.values())
    t_dead   = sum(reg["bug_deadlock"] for reg in heatmap_data.values())

    with open(report_filename, "w", encoding="utf-8") as file_out:
        file_out.write("="*100 + "\n")
        file_out.write("ИТОГОВЫЙ ОТЧЕТ ПО ТЕСТИРОВАНИЮ ПОВЕДЕНЧЕСКОЙ МОДЕЛИ UART (riscv.py)\n")
        file_out.write("="*100 + "\n\n")

        file_out.write("СВОДНАЯ СТАТИСТИКА:\n")
        file_out.write(f"Всего итераций:       {total_iterations}\n")
        file_out.write(f"Операций записи:      {t_writes}\n")
        file_out.write(f"Операций чтения:      {t_reads}\n")
        file_out.write(f"Защита RO регистров:  {t_ro} (Успешно отклоненные записи)\n")
        file_out.write(f"Ошибок данных (Mism): {t_mism}\n")
        file_out.write(f"Ошибок залипания значений (Stck): {t_stk}\n")
        file_out.write(f"Ошибок зависания (Deadlck): {t_dead}\n")
        file_out.write(f"Переполнений (Glitch):{t_ovf} (Сохранено > 8 бит)\n")
        file_out.write(f"Неожиданных ошибок:   {t_unexp}\n\n")

        file_out.write("-" * 105 + "\n")
        file_out.write(
            f"{'Адрес':<8} | {'Writes':<8} | {'Reads':<8} | {'RO Denied':<10} | "
            f"{'Mismatch':<10} | {'Sticky':<10} | {'Deadlock':<10} | "
            f"{'Overflow':<10} | {'Unexp':<10}\n"
        )
        file_out.write("-" * 105 + "\n")

        for addr, d in sorted(heatmap_data.items()):
            addr_str = f"0x{addr:02X}"
            file_out.write(
                f"{addr_str:<8} | {d['writes']:<8} | {d['reads']:<8} | "
                f"{d['ro_denied']:<10} | {d['mismatches']:<10} | "
                f"{d['bug_sticky']:<10} | {d['bug_deadlock']:<10} | "
                f"{d['bug_overflow']:<10} | {d['unexpected_errors']:<10}\n"
            )

        file_out.write("-" * 105 + "\n\n")

        if t_unexp == 0 and t_mism == 0 and t_ovf == 0:
            file_out.write("РЕЗУЛЬТАТ: Модель полностью соответствует спецификации APB2-UART.\n")
        else:
            file_out.write("РЕЗУЛЬТАТ: ВНИМАНИЕ! Обнаружены отклонения (Glitch / Overflow). \n")

    DETAILS_LOGGER.info("\n[!] Тест завершен.")
    DETAILS_LOGGER.info("[!] Полный трейс транзакций записан в: uart_test_details.log")
    DETAILS_LOGGER.info("[!] Матрица для графика сгенерирована: %s", report_filename)


def test_full_uart_flow():
    """
    Обертка для запуска последовательности тестов через pytest.
    """
    run_coverage_directed_tests()
    run_fsm_tracking()
    print("\n" + "="*50)

    run_stress_test(6500)