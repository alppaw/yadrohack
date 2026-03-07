"""
ФИНАЛЬНЫЙ МОДУЛЬ ТЕСТИРОВАНИЯ (GOLDEN VERSION).
Объединяет FSM-трекинг, 100% Coverage тесты и агрессивный поиск багов.
Детектирует: Overflow (0xDEAD), Deadlock (LCR->MCR), Sticky Bit.
+ LOGS RO DENIED (Успешные срабатывания защиты)
"""

import importlib
import json
import logging
import random
import sys

# Импортируем модуль (предполагается, что это обертка над BlackBox или сам BlackBox)
import riscv_br

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
DETAILS_LOGGER = logging.getLogger("details")
DETAILS_LOGGER.setLevel(logging.DEBUG)

# 1. ФАЙЛ (Пишет ВСЮ историю: Debug, Errors, Info)
DETAILS_HANDLER = logging.FileHandler(
    "uart_test_details.log", mode='w', encoding='utf-8'
)
DETAILS_HANDLER.setLevel(logging.DEBUG)
DETAILS_HANDLER.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
DETAILS_LOGGER.addHandler(DETAILS_HANDLER)

# 2. КОНСОЛЬ (Пишет только INFO: Прогресс и Результат)
CONSOLE_HANDLER = logging.StreamHandler(sys.stdout)
CONSOLE_HANDLER.setLevel(logging.INFO)
CONSOLE_HANDLER.addFilter(lambda record: record.levelno == logging.INFO)
CONSOLE_HANDLER.setFormatter(logging.Formatter('>>> %(message)s'))
DETAILS_LOGGER.addHandler(CONSOLE_HANDLER)


# --- ЧАСТЬ 1: НАПРАВЛЕННЫЕ ТЕСТЫ (FSM & COVERAGE) ---

def run_fsm_tracking():
    """
    Генерирует граф состояний (Happy Path + Dark Path) для визуализации.
    """
    DETAILS_LOGGER.info("Запуск трекинга FSM (генерация графа)...")
    importlib.reload(riscv_br) 

    fsm_log = []
    current_state = "RESET_IDLE"

    def transition(new_state):
        nonlocal current_state
        if current_state != new_state:
            fsm_log.append([current_state, new_state])
            DETAILS_LOGGER.debug(f"[FSM] Переход: {current_state} -> {new_state}")
            current_state = new_state

    # 1. Инициализация (DLAB -> Baudrate -> 8N1)
    if riscv_br.reg_access(3, 0x80, "write").get('ack'):
        transition("DLAB_ENABLED")
    
    riscv_br.reg_access(1, 0x0D, "write") 
    riscv_br.reg_access(2, 0x00, "write") 
    transition("BAUDRATE_SET")
    
    if riscv_br.reg_access(3, 0x03, "write").get('ack'):
        transition("OPERATIONAL_READY")

    # 2. Передача данных
    lsr = riscv_br.reg_access(7, 0, "read").get('reg_value', 0)
    if lsr & 0x20:
        transition("TX_WAITING")
        riscv_br.reg_access(0, 0xAA, "write") 
        transition("TX_TRANSMITTING")
        # Эмуляция тиков (если поддерживается моделью)
        if hasattr(riscv_br, 'step_clock'):
            riscv_br.step_clock(5)
        transition("OPERATIONAL_READY")

    # 3. Попытки взлома (Dark Path)
    if not riscv_br.reg_access(7, 0xFF, "write").get('ack'):
        transition("RO_PROTECTION_TRIGGERED")
        transition("OPERATIONAL_READY")

    with open("fsm_transitions.json", "w", encoding="utf-8") as f:
        json.dump(fsm_log, f, indent=4)
    
    DETAILS_LOGGER.info("Граф FSM успешно записан в fsm_transitions.json")


# --- ЧАСТЬ 2: СТРЕСС-ТЕСТ (AGRESSIVE BUG HUNTING) ---

def run_stress_test(iterations=65000):
    """
    Запускает фаззинг с проверкой на Overflow (0xDEAD), Deadlock и Sticky Bit.
    """
    DETAILS_LOGGER.info(f"Запуск стресс-теста: {iterations} итераций...")
    
    # 1. Хард-ресет модуля перед тестом
    importlib.reload(riscv_br)

    # 2. Обертки для удобства
    def uart_write(byte_addr, val):
        return riscv_br.reg_access(byte_addr // 4, val, "write")

    def uart_read(byte_addr):
        return riscv_br.reg_access(byte_addr // 4, 0, "read")

    # 3. Матрица ошибок
    heatmap_data = {
        (i * 4): {
            "writes": 0, "reads": 0, "ro_denied": 0, 
            "mismatches": 0, "bug_sticky": 0, "bug_deadlock": 0, 
            "bug_overflow": 0, "unexpected_errors": 0
        } for i in range(10)
    }

    # Теневая память (Reference Model). Начальные значения:
    # LCR=0x03, IIR=0x01, LSR=0x60
    shadow_memory = {i: 0 for i in range(10)}
    shadow_memory[3] = 0x03
    shadow_memory[5] = 0x01
    shadow_memory[7] = 0x60
    
    # Для отслеживания Sticky (предыдущее значение)
    prev_val = {i: 0 for i in range(10)}


    for i in range(iterations):
        byte_addr = random.randint(0, 9) * 4
        idx = byte_addr // 4
        operation = random.choice(['write', 'read'])
        
        # Проверяем состояние DLAB (бит 7 в LCR/idx=3)
        dlab = (shadow_memory[3] >> 7) & 0x1

        if operation == 'write':
            heatmap_data[byte_addr]["writes"] += 1
            # Генерируем данные > 8 бит, чтобы провоцировать Overflow
            data = random.randint(0, 0x1FF) 
            
            # Логируем попытку записи
            DETAILS_LOGGER.debug(f"Ит {i}: [WRITE] Addr={hex(byte_addr)}, Data={hex(data)}")
            
            response = uart_write(byte_addr, data)
            
            # Проверка Read-Only регистров (5, 7, 9) и за пределами карты (>9)
            if idx in [5, 7, 9] or idx > 9:
                if response.get('ack'):
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                    DETAILS_LOGGER.error(f"Ит {i}: [FAIL] Запись в RO регистр {hex(byte_addr)} прошла успешно!")
                else:
                    heatmap_data[byte_addr]["ro_denied"] += 1
                    # --- ДОБАВЛЕНО ЛОГИРОВАНИЕ УСПЕШНОЙ ЗАЩИТЫ ---
                    DETAILS_LOGGER.debug(f"Ит {i}: [SUCCESS] RO Protection сработала на {hex(byte_addr)}")

            else:
                # Обычные регистры
                if not response.get('ack'):
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                    DETAILS_LOGGER.error(f"Ит {i}: [FAIL] Нет ACK на запись в {hex(byte_addr)}")
                else:
                    # --- ПРОВЕРКА БАГА 3: OVERFLOW GLITCH ---
                    # Логика: Если данные > 0xFF, ожидаем глитч XOR 0xDEAD
                    written_val = response.get('reg_value', 0)
                    
                    if data > 0xFF:
                        expected_data = data & 0xFF
                        if written_val != expected_data:
                            # БИНГО! Это точно наш баг
                            heatmap_data[byte_addr]["bug_overflow"] += 1
                            DETAILS_LOGGER.debug(f"Ит {i}: [BUG FOUND] Overflow Glitch! Записалось {hex(written_val)} вместо {hex(data & 0xFFFF)}")

                    # --- ОБНОВЛЕНИЕ ТЕНЕВОЙ ПАМЯТИ ---
                    val_to_store = data & 0xFF
                    if data > 0xFF:
                        # Если баг сработал, сохраняем глитч
                        val_to_store = (data ^ 0xDEAD) & 0xFF
                    
                    # Физическое усечение до 8 бит (симуляция реальности)
                    val_to_store_8bit = val_to_store & 0xFF

                    if idx == 0 and not dlab: pass # RBR/THR меняются аппаратно
                    elif idx in [1, 2] and not dlab: pass # DLL/DLM недоступны без DLAB
                    else: 
                        shadow_memory[idx] = val_to_store_8bit

        else: # operation == 'read'
            heatmap_data[byte_addr]["reads"] += 1
            
            response = uart_read(byte_addr)
            
            if not response.get('ack'):
                if idx <= 9:
                    # --- ПРОВЕРКА БАГА 2: DEADLOCK ---
                    # Если ACK нет, и мы читали регистры ядра (0-3) -> это Баг
                    if idx <= 3 or idx==7:
                        heatmap_data[byte_addr]["bug_deadlock"] += 1
                        DETAILS_LOGGER.debug(f"Ит {i}: [BUG FOUND] Deadlock")
                    else:
                        heatmap_data[byte_addr]["unexpected_errors"] += 1
                        DETAILS_LOGGER.error(f"Ит {i}: [FAIL] Неожиданный отказ ACK на чтении {hex(byte_addr)}")
            else:

                actual_val = response.get('reg_value', 0)
                
                # Исключаем регистры, которые меняются сами (RBR, LSR)
                # idx=0 проверяем только если FIFO выключен (бит 0 в FCR/Shadow[6] == 0)
                if idx!=7 and idx <= 9 and (idx!=0 or (idx==0 and not(shadow_memory[6] & 0x01))):
                    expected_val = shadow_memory[idx]
                    
                    if actual_val != expected_val:
                        # --- ПРОВЕРКА БАГА 1: STICKY BIT ---
                        # Если текущее значение == предыдущему (залипло), но отличается от ожидаемого
                        if prev_val[idx] == actual_val:
                            heatmap_data[byte_addr]["bug_sticky"] += 1
                            DETAILS_LOGGER.debug(f"Ит {i}: [BUG FOUND] Sticky Bit на {hex(byte_addr)}")
                        else:
                            heatmap_data[byte_addr]["mismatches"] += 1
                            DETAILS_LOGGER.error(f"Ит {i}: [FAIL] Mismatch {hex(byte_addr)}. Ожидалось: {hex(expected_val)}, Получено: {hex(actual_val)}")
                        
                prev_val[idx] = actual_val

        # Продвигаем время (если модель поддерживает)
        if hasattr(riscv_br, 'step_clock') and random.random() < 0.10:
            riscv_br.step_clock(1)

        if i > 0 and i % 10000 == 0:
            DETAILS_LOGGER.info(f"Прогресс: {i} итераций завершено...")

    write_final_report(iterations, heatmap_data)


def write_final_report(total_iterations, heatmap_data):
    """Генерирует финальный отчет."""
    report_filename = "uart_final_summary.txt"
    
    # Суммируем ошибки
    t_stk    = sum(r["bug_sticky"] for r in heatmap_data.values())
    t_dead   = sum(r["bug_deadlock"] for r in heatmap_data.values())
    t_ovf    = sum(r["bug_overflow"] for r in heatmap_data.values())
    t_mism   = sum(r["mismatches"] for r in heatmap_data.values())
    t_unexp  = sum(r["unexpected_errors"] for r in heatmap_data.values())
    
    # --- СУММИРУЕМ RO DENIED ---
    t_ro     = sum(r["ro_denied"] for r in heatmap_data.values())

    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("="*120 + "\n")
        f.write("ИТОГОВЫЙ ОТЧЕТ (FINAL_TEST.PY)\n")
        f.write("="*120 + "\n\n")
        
        # --- ВЫВОДИМ RO DENIED В СВОДКУ ---
        f.write(f"RO Denied (Success Protection): {t_ro}\n")
        f.write(f"Баг #1 (Sticky):           {t_stk}\n")
        f.write(f"Баг #2 (Deadlock):         {t_dead}\n")
        f.write(f"Баг #3 (Overflow):         {t_ovf}\n")
        f.write(f"Неизвестные Mismatch:      {t_mism}\n")
        f.write(f"Неизвестные Ошибки ACK:    {t_unexp}\n\n")
        
        f.write("-" * 120 + "\n")
        # --- ВЫВОДИМ КОЛОНКУ RO Denied ---
        f.write(f"{'Адрес':<8} | {'Writes':<8} | {'Reads':<8} | {'RO Denied':<10} | {'Sticky':<8} | {'Deadlck':<8} | {'Overflw':<8} | {'Mismtch':<8} | {'Unexp':<8}\n")
        f.write("-" * 120 + "\n")
        
        for addr in sorted(heatmap_data.keys()):
            d = heatmap_data[addr]
            addr_str = f"0x{addr:02X}"
            f.write(f"{addr_str:<8} | {d['writes']:<8} | {d['reads']:<8} | {d['ro_denied']:<10} | {d['bug_sticky']:<8} | {d['bug_deadlock']:<8} | {d['bug_overflow']:<8} | {d['mismatches']:<8} | {d['unexpected_errors']:<8}\n")
            
        f.write("-" * 120 + "\n\n")

    DETAILS_LOGGER.info(f"\n[!] Тест завершен. Отчет: {report_filename}")


if __name__ == "__main__":
    # 1. Генерируем граф для дашборда
    run_fsm_tracking()
    print("\n" + "="*50)
    # 2. Ищем баги
    run_stress_test(65000)