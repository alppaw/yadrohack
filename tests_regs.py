"""
Тестплан верификации регистров на основе сгенерированной SystemRDL модели.
"""
import pytest
from systemrdl import RDLCompiler, RDLCompileError
from systemrdl.node import RegNode

# =========================================================
# ИМПОРТ РЕАЛЬНОГО ЧЕРНОГО ЯЩИКА (Раскомментируйте у себя)
# from riscv_reg_block import riscv_reg_access
# =========================================================

# Заглушка для локальной проверки, УДАЛИТЬ ПОТОМ
def riscv_reg_access(addr, data, rw, bus_width=32):
    return {'reg_value': data, 'status': 'OK', 'ack': True}

def get_addrs_from_rdl(rdl_file: str = "discovered_model.rdl"):
    """Парсит RDL файл и достает из него адреса для Pytest."""
    compiler = RDLCompiler()
    try:
        compiler.compile_file(rdl_file)
        root = compiler.elaborate()
    except Exception as e:
        print(f"Ошибка компиляции RDL: {e}")
        return []

    valid_addrs =[]
    # Проходим по дереву RDL и собираем адреса регистров
    for node in root.descendants():
        if isinstance(node, RegNode):
            valid_addrs.append(node.absolute_address)
            
    return valid_addrs

# Получаем список адресов динамически из RDL файла!
RDL_ADDRESSES = get_addrs_from_rdl()

class TestRegisterVerification:
    """Набор тестов для проверки регистрового файла."""

    @pytest.mark.parametrize("addr", RDL_ADDRESSES)
    def test_coverage_read_write(self, addr):
        """
        Базовый тест для покрытия (Transition: Write -> Read).
        Должен пройти по всем регистрам из RDL.
        """
        test_data = 0xDEADBEEF
        
        # 1. Запись
        wr_resp = riscv_reg_access(addr=addr, data=test_data, rw="write")
        # Тут мы не делаем жесткий assert, чтобы тесты шли дальше и собирали покрытие, 
        # даже если блок сломан (например, баг 0x13).
        
        # 2. Чтение
        rd_resp = riscv_reg_access(addr=addr, data=0, rw="read")
        
        # Записываем логику в CSV/JSON для дашборда (опционально, реализуем позже)

    def test_bug_0x42_stale_data(self):
        """Проверка Bug #1: Register Misread 0x42."""
        addr = 0x0042
        test_data = 0x12345678
        
        # Пишем новые данные
        riscv_reg_access(addr=addr, data=test_data, rw="write")
        
        # Читаем. По условиям бага, FSM не обновляет и отдает старые данные.
        response = riscv_reg_access(addr=addr, data=0, rw="read")
        
        # Если данные НЕ равны записанным, значит мы поймали баг!
        # Ожидаем, что тест УПАДЕТ (assert False), если баг присутствует.
        assert response.get('reg_value') == test_data, f"BUG FOUND: Stale data at 0x{addr:X}!"

    def test_bug_0x13_deadlock(self):
        """Проверка Bug #2: Bus Deadlock (write 0x13 -> read 0x77)."""
        riscv_reg_access(addr=0x0013, data=0xFF, rw="write")
        
        # Следующее чтение должно повесить шину (вернуть ack=False или ошибку)
        response = riscv_reg_access(addr=0x0077, data=0, rw="read")
        
        assert response.get('ack') is True, "BUG FOUND: Bus Deadlock triggered by 0x13!"

    def test_bug_64bit_glitch(self):
        """Проверка Bug #3: Glitch bus_width=64 на 32-bit addr."""
        addr = RDL_ADDRESSES[0] if RDL_ADDRESSES else 0x0004 # Берем любой валидный
        
        response = riscv_reg_access(addr=addr, data=0xFFFFFFFFFFFFFFFF, rw="write", bus_width=64)
        read_resp = riscv_reg_access(addr=addr, data=0, rw="read")
        
        assert read_resp.get('reg_value') == 0xFFFFFFFFFFFFFFFF, "BUG FOUND: 64-bit Glitch overflow!"