import random
import logging
import importlib
import riscv_reg_block  # Импортируем сам модуль целиком!

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
    
    # =========================================================
    # 1. ПОЛНЫЙ АППАРАТНЫЙ СБРОС
    
    importlib.reload(riscv_reg_block)
    
    # 3. ЛОКАЛЬНЫЕ ОБЕРТКИ (создаются 1 раз для этого теста)
    def uart_write(byte_addr, data):
        return riscv_reg_block.reg_access(byte_addr // 4, data, "write")

    def uart_read(byte_addr):
        return riscv_reg_block.reg_access(byte_addr // 4, 0, "read")
    # =========================================================

    shadow_memory = [0] * 16
    stats = {
        "total": 0,
        "write_ops": 0,
        "read_ops": 0,
        "unexpected_errors": 0,
        "bug_1_sticky": 0,
        "bug_2_deadlock": 0,
        "bug_3_overflow": 0
    }

    is_locked = False

    # И дальше пошел ваш цикл...
    for i in range(iterations):
        stats["total"] += 1
        byte_addr = random.randint(0, 15) * 4
        idx = byte_addr // 4
        operation = random.choice(['write', 'read'])
        
        if operation == 'write':
            stats["write_ops"] += 1
            data = random.randint(0, 0x1FFFF) 
            response = uart_write(byte_addr, data) # Вызывает свежую локальную обертку!
            
            # ... и так далее, ваш код без изменений ...
            if response.get('ack'):
                expected_val = data & 0xFFFF
                if data > 0xFFFF:
                    expected_val = (data ^ 0xDEAD) & 0xFFFF
                    if response.get('reg_value') == expected_val:
                        stats["bug_3_overflow"] += 1
                
                shadow_memory[idx] = expected_val
                if idx == 3:
                    is_locked = True
            else:
                details_logger.error(f"Ит {i}: Отказ ACK при записи в {hex(byte_addr)}")
                stats["unexpected_errors"] += 1

        else:
            stats["read_ops"] += 1
            response = uart_read(byte_addr)
            
            if not response.get('ack'):
                if is_locked and idx == 4:
                    stats["bug_2_deadlock"] += 1
                else:
                    details_logger.error(f"Ит {i}: Неожиданный отказ ACK на чтении {hex(byte_addr)}")
                    stats["unexpected_errors"] += 1
                continue

            actual_val = response.get('reg_value', 0)
            expected_val = shadow_memory[idx]

            if actual_val != expected_val:
                if idx == 2 and actual_val == 0x42:
                    stats["bug_1_sticky"] += 1
                else:
                    details_logger.error(f"Ит {i}: Ошибка данных в {hex(byte_addr)}! "
                                         f"Ожидалось: {hex(expected_val)}, Получено: {hex(actual_val)}")
                    stats["unexpected_errors"] += 1

        if i > 0 and i % 10000 == 0:
            details_logger.info(f"Прогресс: {i} итераций завершено...")

    # ... конец цикла

    write_final_report(stats)

def write_final_report(stats):
    """Генерирует человекочитаемый отчет в отдельный файл"""
    report_filename = "uart_final_summary.txt"
    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("="*40 + "\n")
        f.write("ИТОГОВЫЙ ОТЧЕТ ПО ТЕСТИРОВАНИЮ UART\n")
        f.write("="*40 + "\n\n")
        f.write(f"Всего итераций:       {stats['total']}\n")
        f.write(f"Операций записи:      {stats['write_ops']}\n")
        f.write(f"Операций чтения:      {stats['read_ops']}\n")
        f.write(f"Неожиданных ошибок:   {stats['unexpected_errors']}\n")
        f.write("\n" + "-"*40 + "\n")
        f.write("СТАТИСТИКА ВЫЯВЛЕННЫХ БАГОВ:\n")
        f.write("-"*40 + "\n")
        f.write(f"Баг #1 (Sticky Read 0x08):   {stats['bug_1_sticky']} раз\n")
        f.write(f"Баг #2 (Deadlock LCR->IER): {stats['bug_2_deadlock']} раз\n")
        f.write(f"Баг #3 (Overflow Glitch):   {stats['bug_3_overflow']} раз\n")
        f.write("\n" + "="*40 + "\n")
        
        if stats['unexpected_errors'] == 0:
            f.write("РЕЗУЛЬТАТ: Успешно. Все отклонения соответствуют известным багам.\n")
        else:
            f.write("РЕЗУЛЬТАТ: ВНИМАНИЕ! Найдены неизвестные ошибки шины.\n")

    print(f"\n[!] Тест завершен. \n[!] Детальный лог: uart_test_details.log \n[!] Итоговый отчет: {report_filename}")

if __name__ == "__main__":
    run_stress_test(65000)