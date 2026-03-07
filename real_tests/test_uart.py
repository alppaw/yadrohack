import pytest
from riscv import reg_access, step_clock, get_memory_data

# --- ТЕСТЫ ИНИЦИАЛИЗАЦИИ И ЧТЕНИЯ ---

def test_initial_state():
    """Проверка сбросовых значений регистров"""
    assert reg_access(3, 0, "read")['reg_value'] == 0x03  # LCR
    assert reg_access(7, 0, "read")['reg_value'] == 0x60  # LSR (THRE=1, TEMT=1)
    assert reg_access(5, 0, "read")['reg_value'] == 0x01  # IIR

def test_invalid_address():
    """Покрытие ветки 'addr not in self._regs'"""
    res = reg_access(99, 0, "read")
    assert res['ack'] is False

def test_invalid_operation():
    """Покрытие ветки финального return {'ack': False}"""
    res = reg_access(0, 0, "fly_to_moon")
    assert res['ack'] is False

# --- ТЕСТЫ ЗАЩИТЫ И ПРАВ ДОСТУПА ---

@pytest.mark.parametrize("ra_addr", [5, 7, 9])
def test_readonly_registers(ra_addr):
    """Покрытие защиты Read-Only регистров"""
    initial = reg_access(ra_addr, 0, "read")['reg_value']
    res = reg_access(ra_addr, 0xFF, "write")
    assert res['ack'] is False
    assert reg_access(ra_addr, 0, "read")['reg_value'] == initial

def test_dlab_protection():
    """Покрытие логики DLAB для DLL/DLM"""
    # 1. DLAB = 0 (по умолчанию)
    reg_access(1, 0xAA, "write") # Пишем в DLL
    assert reg_access(1, 0, "read")['reg_value'] == 0x00 # Запись должна игнорироваться
    
    # 2. Устанавливаем DLAB = 1
    reg_access(3, 0x83, "write")
    reg_access(1, 0x55, "write") # Пишем в DLL
    assert reg_access(1, 0, "read")['reg_value'] == 0x55 # Успех
    
    # Сбрасываем для следующих тестов
    reg_access(3, 0x03, "write")

# --- ТЕСТЫ МАСКИРОВАНИЯ (WLS) ---

@pytest.mark.parametrize("wls, mask", [
    (0, 0x1F), # 5 бит
    (1, 0x3F), # 6 бит
    (2, 0x7F), # 7 бит
    (3, 0xFF), # 8 бит
])
def test_wls_masking(wls, mask):
    """Покрытие функции _get_data_mask и применения маски в THR"""
    reg_access(3, wls, "write") # Устанавливаем режим WLS
    reg_access(0, 0xFF, "write") # Пишем "все единицы"
    step_clock(1)
    
    # Читаем из RBR (Index 0 при DLAB=0)
    res = reg_access(0, 0, "read")
    assert res['reg_value'] == mask

# --- ТЕСТЫ FIFO И ТАЙМИНГА ---

def test_fifo_off_behavior():
    """Покрытие режима FIFO=0: данные уходят в RBR и ставят DR"""
    reg_access(6, 0x00, "write") # FIFO OFF
    reg_access(0, 0x42, "write")
    
    # Проверка LSR в момент "передачи"
    lsr = reg_access(7, 0, "read")['reg_value']
    assert (lsr & 0x60) == 0 # THRE=0, TEMT=0
    
    step_clock(1)
    
    lsr_after = reg_access(7, 0, "read")['reg_value']
    assert lsr_after & 0x01 # DR (Data Ready) должен быть 1
    assert reg_access(0, 0, "read")['reg_value'] == 0x42
    assert not (reg_access(7, 0, "read")['reg_value'] & 0x01) # DR сбросился после чтения

def test_fifo_on_behavior():
    """Покрытие режима FIFO=1: данные уходят в memory"""
    reg_access(6, 0x01, "write") # FIFO ON
    reg_access(0, 0xCC, "write")
    step_clock(1)
    
    assert 0xCC in get_memory_data()

def test_large_data_truncation():
    """Покрытие маскировки 32-бит до 8-бит (data & 0xFF)"""
    reg_access(3, 0x03, "write") # 8-bit mode
    reg_access(4, 0xDEADBEEF, "write") # Пишем в IER
    assert reg_access(4, 0, "read")['reg_value'] == 0xEF

def test_step_clock_multi():
    """Покрытие очереди событий при нескольких шагах"""
    reg_access(0, 0x01, "write")
    # Не шагаем сразу, проверяем, что данные не ушли
    assert reg_access(7, 0, "read")['reg_value'] & 0x60 == 0
    step_clock(5) # Шагаем многократно
    assert reg_access(7, 0, "read")['reg_value'] & 0x60 == 0x60