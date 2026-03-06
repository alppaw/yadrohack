from riscv_reg_block import reg_access


from typing import Dict, Any, List

# --- Константы из спецификации ---
REG_MAP = {
    "RBR_THR": 0x00,
    "DLL":     0x04, # DLAB=1
    "DLM":     0x08, # DLAB=1
    "LCR":     0x0C,
    "IER":     0x10,
    "IIR":     0x14,
    "FCR":     0x18,
    "LSR":     0x1C,
    "MCR":     0x20,
    "MSR":     0x24,
}

# Ожидаемые значения после сброса (согласно спецификации)
# LSR: THRE=1 (0x20), TEMT=1 (0x40) -> 0x60
# LCR: WLS=0x3 -> 0x03
EXPECTED_RESET = {
    "RBR_THR": 0x00000000,
    "LCR":     0x00000003,
    "IER":     0x00000000,
    "LSR":     0x00000060, 
    "FCR":     0x00000000,
    "MCR":     0x00000000,
    # Для IIR, MSR значения могут зависеть от реализации, 
    # обычно IIR=0x01 (no interrupt)
}

def check_lsr(context: str):
    """Служебная функция для проверки LSR в любой момент"""
    res = reg_access(REG_MAP["LSR"], 0, "read")
    val = res.get('data', 0)
    # Проверяем, что нет ошибок (OE, PE, FE, BI) и TX пуст
    # Ожидаем 0x60 (THRE=1, TEMT=1)
    if (val & 0x7F) != 0x60:
        print(f"[LSR CHECK FAILED] at {context}: Got {hex(val)}, Expected 0x60")
    return val

def test_reset_values():
    errors = 0
    
    print("--- Start Reset Value Testing ---")

    # 1. Проверка стандартных регистров (DLAB=0)
    for reg_name, addr in REG_MAP.items():
        # Пропускаем DLL/DLM пока DLAB=0
        if reg_name in ["DLL", "DLM"]: continue
        
        # Перед каждым чтением проверяем LSR
        check_lsr(f"Before reading {reg_name}")
        
        # Читаем целевой регистр
        resp = reg_access(addr, 0, "read")
        actual_val = resp.get('data', 0)
        
        # Проверяем на соответствие
        if reg_name in EXPECTED_RESET:
            expected = EXPECTED_RESET[reg_name]
            if actual_val != expected:
                print(f"[FAIL] {reg_name} (Addr: {hex(addr)}): "
                      f"Got {hex(actual_val)}, Exp {hex(expected)}")
                errors += 1
            else:
                print(f"[OK] {reg_name}: {hex(actual_val)}")

        # Проверяем старшие 24 бита (должны быть 0, т.к. регистры 8-битные в 32-битном поле)
        if (actual_val >> 8) != 0:
            print(f"[FAIL] {reg_name}: Reserved bits [31:8] are NOT zero! Value: {hex(actual_val)}")
            errors += 1

    # 2. Проверка DLL и DLM (нужно переключить DLAB)
    print("\n--- Testing DLL/DLM (DLAB=1) ---")
    
    # Устанавливаем DLAB=1
    reg_access(REG_MAP["LCR"], 0x83, "write") 
    check_lsr("After setting DLAB")

    for reg_name in ["DLL", "DLM"]:
        addr = REG_MAP[reg_name]
        resp = reg_access(addr, 0, "read")
        val = resp.get('data', 0)
        print(f"[OK] {reg_name} (DLAB=1): {hex(val)}")
        if (val >> 8) != 0:
            print(f"[FAIL] {reg_name}: Reserved bits [31:8] not zero")
            errors += 1

    # Возвращаем DLAB=0
    reg_access(REG_MAP["LCR"], 0x03, "write")

    print(f"\nTotal Reset Errors: {errors}")
    return errors

# Запуск
test_reset_values()