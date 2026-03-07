import random
import logging
import importlib
import riscv

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---

details_logger = logging.getLogger("details")
details_logger.setLevel(logging.DEBUG)
details_handler = logging.FileHandler("uart_test_details.log", mode='w', encoding='utf-8')
details_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
details_logger.addHandler(details_handler)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(message)s'))
details_logger.addHandler(console_handler)


# --- ОСНОВНОЙ ТЕСТ ---

def run_stress_test(iterations=65000):
    details_logger.info(f"Запуск стресс-теста: {iterations} итераций...")

    importlib.reload(riscv)

    # 3. ЛОКАЛЬНЫЕ ОБЕРТКИ (создаются 1 раз для этого теста)
    def uart_write(byte_addr, data):
        return riscv.reg_access(byte_addr // 4, data, "write")

    def uart_read(byte_addr):
        return riscv.reg_access(byte_addr // 4, 0, "read")
    # =========================================================
    shadow_memory = [0] * 16
    
    # === ГЛАВНАЯ СТРУКТУРА ДЛЯ HEATMAP ===
    # Создаем словарь статистик для КАЖДОГО из 16 регистров
    heatmap_data = {
        (i * 4): {
            "writes": 0,
            "reads": 0,
            "bug_1_sticky": 0,
            "bug_2_deadlock": 0,
            "bug_3_overflow": 0,
            "unexpected_errors": 0
        } for i in range(16)
    }

    # Флаг состояния лока (строго для текущего запуска)
    is_locked = False

    for i in range(iterations):
        byte_addr = random.randint(0, 15) * 4
        idx = byte_addr // 4
        operation = random.choice(['write', 'read'])
        
        if operation == 'write':
            heatmap_data[byte_addr]["writes"] += 1
            data = random.randint(0, 0x1FFFF) 
            response = uart_write(byte_addr, data)
            
            if response.get('ack'):
                expected_val = data & 0xFFFF
                # Проверка Бага 3 (Overflow)
                if data > 0xFFFF:
                    expected_val = (data ^ 0xDEAD) & 0xFFFF
                    if response.get('reg_value') == expected_val:
                        heatmap_data[byte_addr]["bug_3_overflow"] += 1
                
                shadow_memory[idx] = expected_val
                
                # Строго: фиксируем блокировку только когда сами пишем в LCR (0x0C)
                if idx == 3:
                    is_locked = True
            else:
                details_logger.error(f"Ит {i}: Отказ ACK при записи в {hex(byte_addr)}")
                heatmap_data[byte_addr]["unexpected_errors"] += 1

        else:
            heatmap_data[byte_addr]["reads"] += 1
            response = uart_read(byte_addr)
            
            # Проверка отказов ACK
            if not response.get('ack'):
                # Строгая проверка: засчитываем Баг 2, ТОЛЬКО если мы уверены, 
                # что сами перевели автомат в состояние Deadlock (is_locked == True)
                if is_locked and idx == 4:
                    heatmap_data[byte_addr]["bug_2_deadlock"] += 1
                else:
                    details_logger.error(f"Ит {i}: Неожиданный отказ ACK на чтении {hex(byte_addr)}")
                    heatmap_data[byte_addr]["unexpected_errors"] += 1
                continue

            actual_val = response.get('reg_value', 0)
            expected_val = shadow_memory[idx]

            # Проверка данных и Бага 1 (Sticky)
            if actual_val != expected_val:
                if idx == 2 and actual_val == 0x42:
                    heatmap_data[byte_addr]["bug_1_sticky"] += 1
                else:
                    details_logger.error(f"Ит {i}: Ошибка данных в {hex(byte_addr)}! "
                                         f"Ожидалось: {hex(expected_val)}, Получено: {hex(actual_val)}")
                    heatmap_data[byte_addr]["unexpected_errors"] += 1

        if i > 0 and i % 10000 == 0:
            details_logger.info(f"Прогресс: {i} итераций завершено...")

    write_final_report(iterations, heatmap_data)


def write_final_report(total_iterations, heatmap_data):
    """Генерирует отчет в виде таблицы, идеальной для экспорта в дашборд"""
    report_filename = "uart_final_summary.txt"
    
    # Считаем глобальные тоталы для сводки
    t_writes = sum(reg["writes"] for reg in heatmap_data.values())
    t_reads  = sum(reg["reads"] for reg in heatmap_data.values())
    t_bug1   = sum(reg["bug_1_sticky"] for reg in heatmap_data.values())
    t_bug2   = sum(reg["bug_2_deadlock"] for reg in heatmap_data.values())
    t_bug3   = sum(reg["bug_3_overflow"] for reg in heatmap_data.values())
    t_unexp  = sum(reg["unexpected_errors"] for reg in heatmap_data.values())

    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("="*90 + "\n")
        f.write("ИТОГОВЫЙ ОТЧЕТ ПО ТЕСТИРОВАНИЮ UART (HEATMAP DATA)\n")
        f.write("="*90 + "\n\n")
        
        f.write("СВОДНАЯ СТАТИСТИКА:\n")
        f.write(f"Всего итераций:       {total_iterations}\n")
        f.write(f"Операций записи:      {t_writes}\n")
        f.write(f"Операций чтения:      {t_reads}\n")
        f.write(f"Неожиданных ошибок:   {t_unexp}\n\n")
        
        f.write("-" * 90 + "\n")
        # Заголовок таблицы
        f.write(f"{'Адрес':<8} | {'Writes':<8} | {'Reads':<8} | {'Bug 1 (Stk)':<12} | {'Bug 2 (Dead)':<12} | {'Bug 3 (Ovf)':<12} | {'Unexp':<8}\n")
        f.write("-" * 90 + "\n")
        
        # Вывод данных по каждому регистру
        for addr in sorted(heatmap_data.keys()):
            d = heatmap_data[addr]
            addr_str = f"0x{addr:02X}"
            f.write(f"{addr_str:<8} | {d['writes']:<8} | {d['reads']:<8} | {d['bug_1_sticky']:<12} | {d['bug_2_deadlock']:<12} | {d['bug_3_overflow']:<12} | {d['unexpected_errors']:<8}\n")
            
        f.write("-" * 90 + "\n\n")
        
        if t_unexp == 0:
            f.write("РЕЗУЛЬТАТ: Успешно. Все отклонения соответствуют известным багам.\n")
        else:
            f.write("РЕЗУЛЬТАТ: ВНИМАНИЕ! Найдены неизвестные ошибки шины (см. колонку Unexp).\n")

    print(f"\n[!] Тест завершен. \n[!] Итоговый табличный отчет сгенерирован: {report_filename}")

if __name__ == "__main__":
    run_stress_test(65000)