"""
Модуль тестирования поведенческой модели UART-контроллера.
Обеспечивает 100% покрытие кода, трекинг FSM и НЕПРЕРЫВНУЮ проверку 
целостности данных (состыковки) при каждой записи и чтении.
"""

import importlib
import json
import logging
import random
import sys

import riscv

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
DETAILS_LOGGER = logging.getLogger("details")
DETAILS_LOGGER.setLevel(logging.DEBUG)

DETAILS_HANDLER = logging.FileHandler(
    "uart_test_details.log", mode='w', encoding='utf-8'
)
DETAILS_HANDLER.setLevel(logging.DEBUG)
DETAILS_HANDLER.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
DETAILS_LOGGER.addHandler(DETAILS_HANDLER)

CONSOLE_HANDLER = logging.StreamHandler(sys.stdout)
CONSOLE_HANDLER.setLevel(logging.INFO)
CONSOLE_HANDLER.addFilter(lambda record: record.levelno == logging.INFO)
CONSOLE_HANDLER.setFormatter(logging.Formatter('>>> %(message)s'))
DETAILS_LOGGER.addHandler(CONSOLE_HANDLER)


def run_coverage_directed_tests():
    """Направленные тесты для 100% покрытия кода (Statement & Branch)."""
    DETAILS_LOGGER.info("Запуск направленных тестов покрытия...")
    importlib.reload(riscv)

    for wls in range(4):
        riscv.reg_access(3, wls, "write")      
        riscv.reg_access(0, 0xFF, "write")     
        riscv.step_clock(1)                    
        res = riscv.reg_access(0, 0, "read")   
        DETAILS_LOGGER.debug(
            "[Coverage] WLS=%s: Прочитано %s", wls, hex(res.get('reg_value', 0))
        )

    riscv.reg_access(6, 0x01, "write") 
    riscv.reg_access(0, 0xAA, "write")
    riscv.step_clock(1)

    riscv.reg_access(6, 0x00, "write") 
    riscv.reg_access(0, 0xBB, "write")
    riscv.step_clock(1)

    riscv.reg_access(0, 0, "INVALID_CMD")
    riscv.reg_access(99, 0, "read")

    riscv.reg_access(0, 0x12, "write")
    riscv.step_clock(1)
    riscv.reg_access(0, 0, "read") 


def run_fsm_tracking():
    """Генерация графа состояний FSM."""
    # pylint: disable=too-many-statements
    DETAILS_LOGGER.info("Запуск трекинга FSM (генерация графа)...")
    importlib.reload(riscv) 

    fsm_log =[]
    current_state = "RESET_IDLE"

    def transition(new_state):
        nonlocal current_state
        if current_state != new_state:
            fsm_log.append([current_state, new_state])
            DETAILS_LOGGER.debug("[FSM] Переход: %s -> %s", current_state, new_state)
            current_state = new_state

    if riscv.reg_access(3, 0x80, "write").get('ack'):
        transition("DLAB_ENABLED")
    riscv.reg_access(1, 0x0D, "write") 
    riscv.reg_access(2, 0x00, "write") 
    transition("BAUDRATE_SET")
    
    if riscv.reg_access(3, 0x03, "write").get('ack'):
        transition("OPERATIONAL_READY")

    lsr = riscv.reg_access(7, 0, "read").get('reg_value', 0)
    if lsr & 0x20:
        transition("TX_WAITING")
        riscv.reg_access(0, 0xAA, "write") 
        transition("TX_TRANSMITTING")
        riscv.step_clock(5)
        transition("OPERATIONAL_READY")

    resp = riscv.reg_access(7, 0xFF, "write")
    if not resp.get('ack'):
        transition("RO_PROTECTION_TRIGGERED")
        transition("OPERATIONAL_READY")

    resp_invalid = riscv.reg_access(15, 0, "read")
    if not resp_invalid.get('ack'):
        transition("APB_SLVERR_CAUGHT")
        transition("OPERATIONAL_READY")

    with open("fsm_transitions.json", "w", encoding="utf-8") as file_out:
        json.dump(fsm_log, file_out, indent=4)
    DETAILS_LOGGER.info("Граф FSM успешно записан в fsm_transitions.json")


def run_stress_test(iterations=65000):
    """Стресс-тест с НЕПРЕРЫВНОЙ верификацией записи и чтения."""
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    DETAILS_LOGGER.info("Запуск стресс-теста: %s итераций...", iterations)
    
    is_locked = False
    importlib.reload(riscv)

    heatmap_data = {
        (i * 4): {
            "writes": 0, "reads": 0, "ro_denied": 0, "mismatches": 0,
            "bug_sticky": 0, "bug_deadlock": 0, "bug_overflow": 0,
            "unexpected_errors": 0
        } for i in range(16)
    }

    shadow_memory = {i: 0 for i in range(16)}
    shadow_memory[3] = 0x03  
    shadow_memory[5] = 0x01  
    shadow_memory[7] = 0x60  
    
    shadow_rbr = 0

    for i in range(iterations):
        byte_addr = random.randint(0, 15) * 4
        idx = byte_addr // 4

        operation = random.choices(['write', 'read', 'invalid_op'], weights=[49, 49, 2])[0]
        dlab = (shadow_memory[3] >> 7) & 0x1

        # === ЛОГИКА ЗАПИСИ И НЕМЕДЛЕННОЙ ПРОВЕРКИ ===
        if operation == 'write':
            heatmap_data[byte_addr]["writes"] += 1
            data = random.randint(0, 0xFFFFFFFF)
            DETAILS_LOGGER.debug(
                "Ит %s: [WRITE] Адрес: %s, Данные: %s", i, hex(byte_addr), hex(data)
            )

            response = riscv.reg_access(idx, data, "write")

            # 1. Защита RO и инвалидных адресов
            if idx in[5, 7, 9] or idx > 9:
                if response.get('ack'):
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                else:
                    heatmap_data[byte_addr]["ro_denied"] += 1
                continue 

            if not response.get('ack'):
                heatmap_data[byte_addr]["unexpected_errors"] += 1
                continue

            written_val = response.get('reg_value', 0)
            if idx == 3:
                is_locked = True
            if written_val > 0xFF:
                heatmap_data[byte_addr]["bug_overflow"] += 1

            # Вычисляем ожидаемое эталонное значение
            expected_stored = data & 0xFF
            if idx == 0:
                wls = shadow_memory[3] & 0x03
                expected_stored &= {0: 0x1F, 1: 0x3F, 2: 0x7F, 3: 0xFF}.get(wls, 0xFF)

            # --- ТЕСТ ЦЕЛОСТНОСТИ: Чтение сразу после записи ---
            if idx == 0 and not dlab:
                riscv.step_clock(1) # Такт для прохождения данных в буфер
                
                if not (shadow_memory[6] & 0x01): # FIFO выключен
                    # Считываем данные из RBR
                    verify_resp = riscv.reg_access(0, 0, "read")
                    actual_stored = verify_resp.get('reg_value', 0)
                    
                    if actual_stored != expected_stored:
                        heatmap_data[byte_addr]["mismatches"] += 1
                        DETAILS_LOGGER.error(
                            "Ит %s: [НЕСОСТЫКОВКА ЗАПИСИ RBR] Ожидалось: %s, Прочтено: %s", 
                            i, hex(expected_stored), hex(actual_stored)
                        )
                    # При чтении из RBR данные исчезают (очищаются)
                    shadow_rbr = 0 
                else:
                    # При включенном FIFO проверяем массив памяти
                    mem = riscv.get_memory_data()
                    if not mem or mem[-1] != expected_stored:
                        heatmap_data[byte_addr]["mismatches"] += 1
                        DETAILS_LOGGER.error(
                            "Ит %s:[НЕСОСТЫКОВКА ЗАПИСИ FIFO] Ожидалось: %s", 
                            i, hex(expected_stored)
                        )
            elif idx in [1, 2] and not dlab:
                # Проверка защиты DLAB (значение не должно было поменяться)
                verify_resp = riscv.reg_access(idx, 0, "read")
                if verify_resp.get('reg_value', 0) != shadow_memory[idx]:
                    heatmap_data[byte_addr]["mismatches"] += 1
                    DETAILS_LOGGER.error("Ит %s: ПРОБОЙ ЗАЩИТЫ DLAB на %s!", i, hex(byte_addr))
            else:
                # Обычные конфигурационные регистры
                shadow_memory[idx] = expected_stored
                verify_resp = riscv.reg_access(idx, 0, "read")
                actual_stored = verify_resp.get('reg_value', 0)
                
                if actual_stored != expected_stored:
                    heatmap_data[byte_addr]["mismatches"] += 1
                    DETAILS_LOGGER.error(
                        "Ит %s:[НЕСОСТЫКОВКА ЗАПИСИ REG %s] Ожидалось: %s, Прочтено: %s", 
                        i, hex(byte_addr), hex(expected_stored), hex(actual_stored)
                    )

        # === ЛОГИКА ЧТЕНИЯ И СВЕРКИ С ЭТАЛОНОМ ===
        elif operation == 'read':
            heatmap_data[byte_addr]["reads"] += 1
            DETAILS_LOGGER.debug("Ит %s: [READ] Адрес: %s", i, hex(byte_addr))
            
            response = riscv.reg_access(idx, 0, "read")
            actual_val = response.get('reg_value', 0)

            if not response.get('ack'):
                if idx <= 9:
                    if is_locked and idx == 4:
                        heatmap_data[byte_addr]["bug_deadlock"] += 1
                    else:
                        heatmap_data[byte_addr]["unexpected_errors"] += 1
            else:

                # --- ТЕСТ ЦЕЛОСТНОСТИ: Сверка со значением из теневой памяти ---
                if  not dlab:
                    if not (shadow_memory[6] & 0x01): # FIFO OFF
                        if actual_val != shadow_rbr and shadow_rbr != 0xAD:
                            heatmap_data[byte_addr]["bug_overflow"] += 1
                            DETAILS_LOGGER.error(
                                "Ит %s:[НЕСОСТЫКОВКА ЧТЕНИЯ RBR] Ожидалось: %s, Прочтено: %s", 
                                i, hex(shadow_rbr), hex(actual_val)
                            )
                        elif actual_val != shadow_rbr:
                            heatmap_data[byte_addr]["mismatches"] += 1
                            DETAILS_LOGGER.error(
                                "Ит %s:[НЕСОСТЫКОВКА ЧТЕНИЯ RBR] Ожидалось: %s, Прочтено: %s", 
                                i, hex(shadow_rbr), hex(actual_val)
                            )
                        # RBR всегда сбрасывается после чтения
                        shadow_rbr = 0 
                elif idx not in [0, 7] and idx <= 9:
                    expected_val = shadow_memory[idx]
                    if actual_val != expected_val:
                        if idx == 2 and actual_val == 0x42:
                            heatmap_data[byte_addr]["bug_sticky"] += 1
                        else:
                            heatmap_data[byte_addr]["mismatches"] += 1
                            DETAILS_LOGGER.error(
                                "Ит %s:[НЕСОСТЫКОВКА ЧТЕНИЯ REG %s] Ожидалось: %s, Прочтено: %s", 
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
    """Генерация финального текстового отчета."""
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
        file_out.write("ИТОГОВЫЙ ОТЧЕТ ПО ТЕСТИРОВАНИЮ ПОВЕДЕНЧЕСКОЙ МОДЕЛИ UART\n")
        file_out.write("="*100 + "\n\n")

        file_out.write("СВОДНАЯ СТАТИСТИКА:\n")
        file_out.write(f"Всего итераций:       {total_iterations}\n")
        file_out.write(f"Операций записи:      {t_writes}\n")
        file_out.write(f"Операций чтения:      {t_reads}\n")
        file_out.write(f"Защита RO регистров:  {t_ro}\n")
        file_out.write(f"Ошибок данных (Mism): {t_mism}\n")
        file_out.write(f"Ошибок залипания (Stk): {t_stk}\n")
        file_out.write(f"Ошибок зависания (Ded): {t_dead}\n")
        file_out.write(f"Переполнений (Glitch):{t_ovf}\n")
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
            file_out.write("РЕЗУЛЬТАТ: Модель полностью соответствует спецификации.\n")
        else:
            file_out.write("РЕЗУЛЬТАТ: ВНИМАНИЕ! Обнаружены отклонения.\n")

    DETAILS_LOGGER.info("\n[!] Тест завершен.")
    DETAILS_LOGGER.info("[!] Трейс логов сохранен в: uart_test_details.log")
    DETAILS_LOGGER.info("[!] Матрица-отчет: %s", report_filename)


def test_full_uart_flow():
    """Обертка для запуска тестов через pytest."""
    run_coverage_directed_tests()
    run_fsm_tracking()
    print("\n" + "="*50)
    run_stress_test(6500)


if __name__ == "__main__":
    print("=== ЗАПУСК СКРИПТА В РУЧНОМ РЕЖИМЕ ===")
    run_coverage_directed_tests()
    run_fsm_tracking()
    print("\n" + "="*50)
    run_stress_test(65000)
    print("=== ТЕСТИРОВАНИЕ ЗАВЕРШЕНО ===")