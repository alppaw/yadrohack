from riscv_reg_block import reg_access

from typing import Dict, Any, List

import random
import itertools

def uart_read(addr):
    res = reg_access(addr, 0, "read")
    
    # 1. Извлекаем поле 'data'
    val = res.get('data', 0)
    
    # 2. Если 'data' оказался словарем, достаем из него 'value' или первое значение
    if isinstance(val, dict):
        # Попробуйте 'value' — это стандарт для многих RISC-V тестбенчей
        val = val.get('value', 0) 
        
    return int(val) # Принудительно превращаем в число

def uart_write(addr, data):
    # Убеждаемся, что передаем в reg_access именно число
    if isinstance(data, dict):
        data = data.get('value', data)
    return reg_access(addr, int(data), "write")

def calculate_crc8(data: list) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ 0x07 # Полином x8 + x2 + x + 1
            else:
                crc <<= 1
            crc &= 0xFF
    return crc

# --- Настройки протокола ---
def get_packet(addr, cmd, data_bytes):
    """Формирует пакет [ADDR][CMD][LEN][DATA...][CRC8]"""
    length = len(data_bytes)
    packet = [addr, cmd, length] + data_bytes
    crc = calculate_crc8(packet)
    packet.append(crc)
    return packet

def run_parameter_suite():
    # Опеределяем наборы параметров для проверки
    # (DLL, DLM, LCR_Parity_Bits)
    configs = [
        (0x0D, 0x00, 0x03), # 115200, 8N1
        (0x1A, 0x00, 0x0B), # 57600, 8P1 (Odd Parity)
        (0x68, 0x00, 0x1B), # 14400, 8P1 (Even Parity)
        (0x01, 0x00, 0x03), # Максимальная скорость
    ]

    for dll, dlm, lcr in configs:
        print(f"\n=== ТЕСТИРОВАНИЕ КОНФИГУРАЦИИ: DLL={hex(dll)}, LCR={hex(lcr)} ===")
        
        # 1. Применяем конфигурацию
        setup_uart(dll, dlm, lcr)
        
        # 2. Запускаем серию тестов "Запись-Чтение-Запись" внутри этой конфигурации
        for iteration in range(5): # Для примера 5 циклов на одну конфигу
            print(f"  Итерация данных {iteration}:")
            
            # Генерируем два разных набора данных, чтобы проверить смену
            data_v1 = [random.randint(0, 255) for _ in range(3)]
            data_v2 = [random.randint(0, 255) for _ in range(3)]
            
            # --- ШАГ 1: ЗАПИСЬ И ЧТЕНИЕ ПЕРВОГО НАБОРА ---
            packet1 = get_packet(addr=0x20, cmd=0x02, data_bytes=data_v1)
            send_and_verify(packet1, "First Write")
            
            # --- ШАГ 2: ЗАПИСЬ И ЧТЕНИЕ ВТОРОГО НАБОРА (Проверка обновления) ---
            packet2 = get_packet(addr=0x20, cmd=0x02, data_bytes=data_v2)
            send_and_verify(packet2, "Second Write (New Data)")

def setup_uart(dll, dlm, lcr):
    """Инициализация контроллера"""
    uart_write(0x0C, 0x80) # DLAB=1
    uart_write(0x04, dll)
    uart_write(0x08, dlm)
    uart_write(0x0C, lcr)  # DLAB=0 + формат кадра
    uart_write(0x18, 0x00) # FIFO OFF
    
    # Проверка LSR после инициализации
    lsr = uart_read(0x1C)
    if not (lsr & 0x60): # THRE и TEMT должны быть 1
        print(f"    [WARN] UART не готов после сброса: LSR={hex(lsr)}")

def send_and_verify(packet, label):
    """Отправляет пакет по байту и сразу вычитывает его (Loopback режим)"""
    received = []
    
    for i, byte_to_send in enumerate(packet):
        # Ждем пока передатчик освободится
        if not wait_for_bit(0x1C, 0x20): # LSR[5] (THRE)
            print(f"    [ERR] {label}: TX Timeout на байте {i}")
            return False
        
        # ЗАПИСЬ
        uart_write(0x00, byte_to_send)
        
        # Ждем появления данных в приемнике
        if not wait_for_bit(0x1C, 0x01): # LSR[0] (DR)
            print(f"    [ERR] {label}: RX Timeout на байте {i}")
            return False
            
        # ЧТЕНИЕ
        byte_received = uart_read(0x00) & 0xFF
        received.append(byte_received)
        
        # Проверка ошибок линии в процессе
        lsr = uart_read(0x1C)
        if lsr & 0x0E: # OE, PE, FE
            print(f"    [ERR] {label}: Ошибка LSR={hex(lsr)} на байте {hex(byte_to_send)}")

    # Сравнение
    if packet == received:
        print(f"    [OK] {label}: Данные совпали ({len(packet)} байт)")
        return True
    else:
        print(f"    [FAIL] {label}: Ошибка верификации!")
        print(f"      Sent: {packet}")
        print(f"      Recv: {received}")
        return False

def wait_for_bit(addr, bit_mask, timeout=5000):
    """Ожидание конкретного бита в регистре"""
    for _ in range(timeout):
        val = uart_read(addr)
        if val & bit_mask:
            return True
    return False

# --- Запуск ---
run_parameter_suite()


def diagnostic_test():
    print("=== ЗАПУСК ДИАГНОСТИКИ ШИНЫ И РЕГИСТРОВ ===")
    
    # 1. Проверка записи в IER (этот регистр обычно проще всего)
    # Запишем туда 0x05 (Enable RX и Error IRQ)
    test_val = 0x05
    uart_write(0x10, test_val)
    read_back = uart_read(0x10) & 0xFF
    
    if read_back == test_val:
        print(f"[OK] Шина работает: Записано в IER {hex(test_val)}, прочитано {hex(read_back)}")
    else:
        print(f"[FAIL] Шина НЕ работает: Записано {hex(test_val)}, прочитано {hex(read_back)}")
        return

    # 2. Проверка DLAB и делителя DLL
    uart_write(0x0C, 0x80) # Включаем DLAB
    uart_write(0x04, 0xAA) # Пишем в DLL
    dll_val = uart_read(0x04) & 0xFF
    uart_write(0x0C, 0x00) # Выключаем DLAB
    
    if dll_val == 0xAA:
        print(f"[OK] Регистры делителя (DLL) работают и DLAB переключается")
    else:
        print(f"[FAIL] Ошибка DLAB или DLL: Прочитано {hex(dll_val)} вместо 0xAA")

    # 3. Анализ LSR
    lsr = uart_read(0x1C)
    print(f"Текущий LSR: {hex(lsr)}")
    if not (lsr & 0x20):
        print("[!] ВНИМАНИЕ: Бит THRE (5-й) равен 0. Контроллер считает, что передатчик занят.")
        print("    Это причина всех TX Timeout. Проверьте Reset и Clock в RTL.")

diagnostic_test()