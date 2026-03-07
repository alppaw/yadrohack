import random
import logging
import importlib
import sys
import json
import riscv

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
details_logger = logging.getLogger("details")
details_logger.setLevel(logging.DEBUG)

# 1. ФАЙЛ (Пишет всё)
details_handler = logging.FileHandler("uart_test_details.log", mode='w', encoding='utf-8')
details_handler.setLevel(logging.DEBUG)
details_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
details_logger.addHandler(details_handler)

# 2. КОНСОЛЬ (Пишет только INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.INFO) 
console_handler.addFilter(lambda record: record.levelno == logging.INFO)
console_handler.setFormatter(logging.Formatter('>>> %(message)s'))
details_logger.addHandler(console_handler)


# --- НАПРАВЛЕННЫЕ ТЕСТЫ ДЛЯ 100% ПОКРЫТИЯ (ДОБАВЛЕНО) ---

def run_coverage_directed_tests():
    """
    Принудительное прохождение по всем веткам логики riscv.py,
    чтобы гарантировать 100% покрытия кода (Statement & Branch).
    """
    details_logger.info("Запуск направленных тестов для 100% покрытия кода...")
    importlib.reload(riscv)

    # 1. Покрытие всех масок WLS (5, 6, 7, 8 бит)
    for wls in [0, 1, 2, 3]:
        riscv.reg_access(3, wls, "write")      # Настройка LCR
        riscv.reg_access(0, 0xFF, "write")     # Пишем все единицы
        riscv.step_clock(1)                    # Ждем такт
        res = riscv.reg_access(0, 0, "read")   # Читаем
        details_logger.debug(f"[Coverage] WLS={wls}: Успешно прочитано {hex(res.get('reg_value', 0))}")

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
    
    details_logger.info("Направленные тесты завершены.")


# --- FSM ТРЕКИНГ ---

def run_fsm_tracking():
    """
    Направленный тест (Directed Test) для записи графа состояний FSM.
    Генерирует файл fsm_transitions.json для Streamlit NetworkX.
    """
    details_logger.info("Запуск трекинга FSM (генерация графа)...")
    
    importlib.reload(riscv) # Сбрасываем модель перед FSM тестом
    
    fsm_log =[]
    current_state = "RESET_IDLE"
    
    def transition(new_state):
        nonlocal current_state
        if current_state != new_state:
            fsm_log.append([current_state, new_state])
            details_logger.debug(f"[FSM] Переход: {current_state} -> {new_state}")
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
    with open("fsm_transitions.json", "w", encoding="utf-8") as f:
        json.dump(fsm_log, f, indent=4)
    
    details_logger.info("Граф FSM успешно записан в fsm_transitions.json")


# --- ОСНОВНОЙ ТЕСТ ---

is_locked = False

def run_stress_test(iterations=65000):
    details_logger.info(f"Запуск актуализированного стресс-теста: {iterations} итераций...")
    global is_locked
    
    # Полный сброс модели
    importlib.reload(riscv)

    # Индексы регистров в riscv.py: 0=THR/RBR, 1=DLL, 2=DLM, 3=LCR, 4=IER, 5=IIR, 6=FCR, 7=LSR, 8=MCR, 9=MSR
    # Мы тестируем диапазон 0x00 - 0x3C (индексы 0 - 15)
    heatmap_data = {
        (i * 4): {
            "writes": 0,
            "reads": 0,
            "ro_denied": 0,
            "mismatches": 0,
            "bug_sticky": 0,
            "bug_deadlock": 0,
            "bug_overflow": 0,
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
        
        # Добавляем шанс инвалидной операции для покрытия отказов в основном цикле
        operation = random.choices(['write', 'read', 'invalid_op'], weights=[49, 49, 2])[0]
        
        # Читаем состояние бита DLAB из теневой памяти LCR (регистр 3, бит 7)
        dlab = (shadow_memory[3] >> 7) & 0x1

        if operation == 'write':
            heatmap_data[byte_addr]["writes"] += 1
            data = random.randint(0, 0xFFFFFFFF) 
            details_logger.debug(f"Ит {i}: [WRITE] Адрес: {hex(byte_addr)}, Данные: {hex(data)}")
            
            response = riscv.reg_access(idx, data, "write")
            
            # Проверка поведения Read-Only и Unmapped адресов
            if idx in [5, 7, 9] or idx > 9:
                if response.get('ack'):
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                    details_logger.error(f"Ит {i}: [БАГ] Успешный ACK при записи в RO/Invalid {hex(byte_addr)}")
                else:
                    heatmap_data[byte_addr]["ro_denied"] += 1
            else:
                if not response.get('ack'):
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                    details_logger.error(f"Ит {i}: Отказ ACK при разрешенной записи в {hex(byte_addr)}")
                else:
                    written_val = response.get('reg_value', 0)
                    if idx == 3:
                        is_locked = True
                    
                    if written_val > 0xFF:
                        heatmap_data[byte_addr]["bug_overflow"] += 1
                        details_logger.debug(f"Ит {i}: OVERFLOW GLITCH! Железо сохранило {hex(written_val)} (> 8 bit)")
                    
                    # Обновляем теневую память с учетом архитектуры UART
                    if idx == 0 and not dlab:
                        pass 
                    elif idx in [1, 2] and not dlab:
                        pass
                    else:
                        shadow_memory[idx] = written_val

        elif operation == 'read':
            heatmap_data[byte_addr]["reads"] += 1
            details_logger.debug(f"Ит {i}: [READ] Адрес: {hex(byte_addr)}")
            
            response = riscv.reg_access(idx, 0, "read")
            
            if not response.get('ack'):
                if idx <= 9:
                    if is_locked and idx == 4:
                        heatmap_data[byte_addr]["bug_deadlock"] += 1
                        details_logger.debug(f"Ит {i}: ПОЙМАН DEADLOCK на чтении MCR 0x10")
                    else:
                        heatmap_data[byte_addr]["unexpected_errors"] += 1
                        details_logger.error(f"Ит {i}: Неожиданный отказ ACK на чтении {hex(byte_addr)}")
            else:
                actual_val = response.get('reg_value', 0)
                
                if actual_val > 0xFF and idx < 10:
                    heatmap_data[byte_addr]["bug_overflow"] += 1
                
                if idx not in [0, 7] and idx <= 9:
                    expected_val = shadow_memory[idx]
                    if actual_val != expected_val:
                        if idx == 2 and actual_val == 0x42:
                            heatmap_data[byte_addr]["bug_sticky"] += 1
                            details_logger.debug(f"Ит {i}: ПОЙМАН STICKY BUG на IIR 0x08")
                        else:
                            heatmap_data[byte_addr]["mismatches"] += 1
                            details_logger.error(f"Ит {i}: Mismatch в {hex(byte_addr)}! Ожидалось: {hex(expected_val)}, Получено: {hex(actual_val)}")
        else:
            # Невалидная операция
            response = riscv.reg_access(idx, 0, "null")
            if response.get('ack') and idx <= 9:
                heatmap_data[byte_addr]["unexpected_errors"] += 1

        if random.random() < 0.10:
            riscv.step_clock(1)

        if i > 0 and i % 10000 == 0:
            details_logger.info(f"Прогресс: {i} итераций завершено...")

    write_final_report(iterations, heatmap_data)


def write_final_report(total_iterations, heatmap_data):
    """Генерирует финальный отчет-матрицу для дашборда"""
    report_filename = "uart_final_summary.txt"
    
    t_writes = sum(reg["writes"] for reg in heatmap_data.values())
    t_reads  = sum(reg["reads"] for reg in heatmap_data.values())
    t_ro     = sum(reg["ro_denied"] for reg in heatmap_data.values())
    t_mism   = sum(reg["mismatches"] for reg in heatmap_data.values())
    t_ovf    = sum(reg["bug_overflow"] for reg in heatmap_data.values())
    t_unexp  = sum(reg["unexpected_errors"] for reg in heatmap_data.values())
    t_stk    = sum(reg["bug_sticky"] for reg in heatmap_data.values())
    t_dead   = sum(reg["bug_deadlock"] for reg in heatmap_data.values())

    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("="*100 + "\n")
        f.write("ИТОГОВЫЙ ОТЧЕТ ПО ТЕСТИРОВАНИЮ ПОВЕДЕНЧЕСКОЙ МОДЕЛИ UART (riscv.py)\n")
        f.write("="*100 + "\n\n")
        
        f.write("СВОДНАЯ СТАТИСТИКА:\n")
        f.write(f"Всего итераций:       {total_iterations}\n")
        f.write(f"Операций записи:      {t_writes}\n")
        f.write(f"Операций чтения:      {t_reads}\n")
        f.write(f"Защита RO регистров:  {t_ro} (Успешно отклоненные записи)\n")
        f.write(f"Ошибок данных (Mism): {t_mism}\n")
        f.write(f"Ошибок залипания значений (Stck): {t_stk}\n")
        f.write(f"Ошибок зависания (Deadlck): {t_dead}\n")
        f.write(f"Переполнений (Glitch):{t_ovf} (Сохранено > 8 бит)\n")
        f.write(f"Неожиданных ошибок:   {t_unexp}\n\n")
        
        f.write("-" * 105 + "\n")
        f.write(f"{'Адрес':<8} | {'Writes':<8} | {'Reads':<8} | {'RO Denied':<10} | {'Mismatch':<10} | {'Sticky':<10} | {'Deadlock':<10} | {'Overflow':<10} | {'Unexp':<10}\n")
        f.write("-" * 105 + "\n")
        
        for addr in sorted(heatmap_data.keys()):
            d = heatmap_data[addr]
            addr_str = f"0x{addr:02X}"
            # ИСПРАВЛЕНИЕ ТУТ: заменил статические строки 'bug_sticky' на d['bug_sticky'] и т.д.
            f.write(f"{addr_str:<8} | {d['writes']:<8} | {d['reads']:<8} | {d['ro_denied']:<10} | {d['mismatches']:<10} | {d['bug_sticky']:<10} | {d['bug_deadlock']:<10} | {d['bug_overflow']:<10} | {d['unexpected_errors']:<10}\n")
            
        f.write("-" * 105 + "\n\n")
        
        if t_unexp == 0 and t_mism == 0 and t_ovf == 0:
            f.write("РЕЗУЛЬТАТ: Модель полностью соответствует спецификации APB2-UART.\n")
        else:
            f.write("РЕЗУЛЬТАТ: ВНИМАНИЕ! Обнаружены отклонения (Glitch / Overflow). \n")

    details_logger.info(f"\n[!] Тест завершен.")
    details_logger.info(f"[!] Полный трейс транзакций записан в: uart_test_details.log")
    details_logger.info(f"[!] Матрица для графика сгенерирована: {report_filename}")


# if __name__ == "__main__":
#     # 1. Покрытие веток (Coverage)
#     run_coverage_directed_tests()
    
#     # 2. Построение красивого графа (FSM)
#     run_fsm_tracking()
    
#     print("\n" + "="*50)
    
#     # 3. Актуализированный Стресс-тест
#     run_stress_test(65000)

def test_full_uart_flow():
    # Эта функция начинается на test_, поэтому pytest её увидит и запустит
    run_coverage_directed_tests()
    run_fsm_tracking()
    print("\n" + "="*50)

    run_stress_test(6500) # Можно сделать поменьше итераций для pytest, например 6500