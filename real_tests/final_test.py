import random
import logging
from riscv_reg_block import reg_access

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---

# 1. Логгер для детальных записей (Ошибки и итерации)
details_logger = logging.getLogger("details")
details_logger.setLevel(logging.DEBUG)
details_handler = logging.FileHandler("uart_test_details.log", mode='w', encoding='utf-8')
details_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
details_logger.addHandler(details_handler)

# 2. Логгер для консоли (чтобы видеть прогресс)
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(message)s'))
details_logger.addHandler(console_handler)

# --- ОБЕРТКИ ДОСТУПА ---

def uart_write(byte_addr, data):
    idx = byte_addr // 4
    return reg_access(idx, data, "write")

def uart_read(byte_addr):
    idx = byte_addr // 4
    return reg_access(idx, 0, "read")

# --- ОСНОВНОЙ ТЕСТ ---

def run_stress_test(iterations=65000):
    details_logger.info(f"Запуск стресс-теста: {iterations} итераций...")
    
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

    last_write_addr = None

    for i in range(iterations):
        stats["total"] += 1
        byte_addr = random.randint(0, 15) * 4
        idx = byte_addr // 4
        operation = random.choice(['write', 'read'])
        
        if operation == 'write':
            stats["write_ops"] += 1
            data = random.randint(0, 0x1FFFF) 
            response = uart_write(byte_addr, data)
            
            if response.get('ack'):
                # Предсказываем значение с учетом Бага 3 (Overflow)
                expected_val = data & 0xFFFF
                if data > 0xFFFF:
                    expected_val = (data ^ 0xDEAD) & 0xFFFF
                    if response.get('reg_value') == expected_val:
                        stats["bug_3_overflow"] += 1
                
                shadow_memory[idx] = expected_val
                last_write_addr = idx
            else:
                details_logger.error(f"Ит {i}: Отказ ACK при записи в {hex(byte_addr)}")
                stats["unexpected_errors"] += 1

        else:
            stats["read_ops"] += 1
            response = uart_read(byte_addr)
            
            # Проверка Бага 2: Deadlock
            if not response.get('ack'):
                if last_write_addr == 3 and idx == 4:
                    stats["bug_2_deadlock"] += 1
                else:
                    details_logger.error(f"Ит {i}: Неожиданный отказ ACK на чтении {hex(byte_addr)}")
                    stats["unexpected_errors"] += 1
                continue

            actual_val = response.get('reg_value', 0)
            expected_val = shadow_memory[idx]

            # Проверка данных и Бага 1 (Sticky)
            if actual_val != expected_val:
                if idx == 2 and actual_val == 0x42:
                    stats["bug_1_sticky"] += 1
                else:
                    details_logger.error(f"Ит {i}: Ошибка данных в {hex(byte_addr)}! "
                                         f"Ожидалось: {hex(expected_val)}, Получено: {hex(actual_val)}")
                    stats["unexpected_errors"] += 1

        if i > 0 and i % 10000 == 0:
            details_logger.info(f"Прогресс: {i} итераций завершено...")

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