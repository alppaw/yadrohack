"""
Модуль сканирования адресного пространства RISC-V регистров.
Задача: Найти все валидные адреса в диапазоне 0x0000 - 0xFFFF (65k).
Результат сохраняется в файл valid_regs.json для дальнейшего Coverage-анализа.
"""

import json
import logging
from typing import List


# Настройка логирования для красивого вывода в консоль
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# =====================================================================
# ВНИМАНИЕ: ВРЕМЕННАЯ ЗАГЛУШКА ДО 18:00!
# Как только дадут реальный файл, УДАЛИТЕ эту функцию 
# и РАСКОММЕНТИРУЙТЕ строку импорта ниже:
# from riscv_reg_block import riscv_reg_access
# =====================================================================
# def riscv_reg_access(addr: int, data: int, rw: str, bus_width: int = 32) -> dict:
#     """Временный 'черный ящик' для проверки работы сканера."""
#     # Имитируем, что валидные регистры идут с шагом 4 (типично для 32-bit систем)
#     # И добавим искусственно адреса с багами из ТЗ (0x13, 0x42, 0x77)
#     valid_mock_addrs =[0x13, 0x42, 0x77]
#     if (addr % 4 == 0 and addr <= 0x0A00) or addr in valid_mock_addrs:
#         return {'reg_value': 0, 'status': 'OK', 'ack': True}
#     return {'reg_value': 0, 'status': 'ERROR', 'ack': False}
# # =====================================================================


def scan_registers(start_addr: int = 0x0000, end_addr: int = 0xFFFF) -> List[int]:
    """
    Проходит по всему адресному пространству, выполняя 'read'.
    Если регистр отвечает ACK (True) или статусом OK, считаем его валидным.
    
    Почему 'read'? Чтение безопасно и не спровоцирует случайный deadlock
    раньше времени (в отличие от случайной записи).
    """
    valid_addresses =[]
    logging.info("Начинаем сканирование пространства от 0x%04X до 0x%04X...", start_addr, end_addr)

    for addr in range(start_addr, end_addr + 1):
        try:
            # Делаем безопасное чтение. Дефолтные данные = 0, ширина = 32
            response = riscv_reg_access(addr=addr, data=0, rw="read", bus_width=32)
            
            # Проверяем успешность ответа
            if response.get("ack") is True or response.get("status") == "OK":
                valid_addresses.append(addr)
                
        except Exception as e: # pylint: disable=broad-except
            # На случай, если "черный ящик" выкинет жесткий Exception
            logging.debug("Адрес 0x%04X вызвал ошибку: %s", addr, e)

    logging.info("Сканирование завершено. Найдено рабочих регистров: %d", len(valid_addresses))
    return valid_addresses


def save_to_json(data: List[int], filename: str = "valid_regs.json") -> None:
    """
    Сохраняет список найденных адресов в JSON файл.
    """
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logging.info("Список адресов успешно сохранен в %s", filename)
    except IOError as e:
        logging.error("Ошибка при сохранении файла: %s", e)


if __name__ == "__main__":
    # 1. Запускаем сканирование
    found_regs = scan_registers()
    
    # 2. Сохраняем результат
    if found_regs:
        save_to_json(found_regs)
    else:
        logging.warning("Не найдено ни одного регистра! Проверьте подключение к модулю.")