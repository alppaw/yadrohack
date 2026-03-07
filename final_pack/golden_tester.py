
import importlib
import json
import logging
import random
import sys
import os

# Импортируем модуль (предполагается, что это обертка над BlackBox или сам BlackBox)
import riscv_br

# --- КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ ---
def setup_logging():
    """Настраивает логгеры для файла и консоли."""
    logger = logging.getLogger("details")
    logger.setLevel(logging.DEBUG)
    
    # Очистка предыдущих хендлеров, если есть (для перезагрузки)
    if logger.hasHandlers():
        logger.handlers.clear()

    # 1. ФАЙЛ (Пишет ВСЮ историю: Debug, Errors, Info)
    file_handler = logging.FileHandler(
        "uart_test_details.log", mode='w', encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    logger.addHandler(file_handler)

    # 2. КОНСОЛЬ (Пишет только INFO: Прогресс и Результат)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.addFilter(lambda record: record.levelno == logging.INFO)
    console_handler.setFormatter(logging.Formatter('>>> %(message)s'))
    logger.addHandler(console_handler)
    
    return logger

DETAILS_LOGGER = setup_logging()



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
            DETAILS_LOGGER.debug("[FSM] Переход: %s -> %s", current_state, new_state)
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



def run_stress_test(iterations=65000):
    """
    Запускает фаззинг с проверкой на Overflow (0xDEAD), Deadlock и Sticky Bit.
    """
    DETAILS_LOGGER.info("Запуск стресс-теста: %d итераций...", iterations)

    # 1. Хард-ресет модуля перед тестом
    importlib.reload(riscv_br)

    # 2. Матрица ошибок
    heatmap_data = {
        (i * 4): {
            "writes": 0, "reads": 0, "ro_denied": 0,
            "mismatches": 0, "bug_sticky": 0, "bug_deadlock": 0,
            "bug_overflow": 0, "unexpected_errors": 0
        } for i in range(10)
    }

    # Теневая память (Reference Model). Начальные значения:
    shadow_memory = {i: 0 for i in range(10)}
    shadow_memory[3] = 0x03
    shadow_memory[5] = 0x01
    shadow_memory[7] = 0x60

    # Для отслеживания Sticky (предыдущее значение)
    prev_val = {i: 0 for i in range(10)}

    # Вспомогательная функция для одной итерации (Closure)
    def process_iteration(i):
        byte_addr = random.randint(0, 9) * 4
        idx = byte_addr // 4
        operation = random.choice(['write', 'read'])
        dlab = (shadow_memory[3] >> 7) & 0x1

        if operation == 'write':
            _handle_stress_write(i, byte_addr, idx, dlab, heatmap_data, shadow_memory)
        else:
            _handle_stress_read(i, byte_addr, idx, heatmap_data, shadow_memory, prev_val)

        # Продвигаем время (если модель поддерживает)
        if hasattr(riscv_br, 'step_clock') and random.random() < 0.10:
            riscv_br.step_clock(1)

    for i in range(iterations):
        process_iteration(i)
        if i > 0 and i % 10000 == 0:
            DETAILS_LOGGER.info("Прогресс: %d итераций завершено...", i)

    write_final_report(heatmap_data)


def _handle_stress_write(i, byte_addr, idx, dlab, heatmap_data, shadow_memory):
    """Обработка операции записи внутри стресс-теста."""
    heatmap_data[byte_addr]["writes"] += 1
    # Генерируем данные > 8 бит, чтобы провоцировать Overflow
    data = random.randint(0, 0x1FF)

    DETAILS_LOGGER.debug(
        "Ит %d: [WRITE] Addr=%s, Data=%s", i, hex(byte_addr), hex(data)
    )

    response = riscv_br.reg_access(idx, data, "write")

    # Проверка Read-Only регистров (5, 7, 9) и за пределами карты (>9)
    if idx in [5, 7, 9] or idx > 9:
        if response.get('ack'):
            heatmap_data[byte_addr]["unexpected_errors"] += 1
            DETAILS_LOGGER.error(
                "Ит %d:[FAIL] Запись в RO регистр %s прошла успешно!", i, hex(byte_addr)
            )
        else:
            heatmap_data[byte_addr]["ro_denied"] += 1
            DETAILS_LOGGER.debug(
                "Ит %d: [SUCCESS] RO Protection сработала на %s", i, hex(byte_addr)
            )
    else:
        # Обычные регистры
        if not response.get('ack'):
            heatmap_data[byte_addr]["unexpected_errors"] += 1
            DETAILS_LOGGER.error(
                "Ит %d: [FAIL] Нет ACK на запись в %s", i, hex(byte_addr)
            )
        else:
            _check_overflow_bug(i, byte_addr, data, response, heatmap_data)
            _update_shadow_memory(idx, data, dlab, shadow_memory)


def _check_overflow_bug(i, byte_addr, data, response, heatmap_data):
    """Проверка бага Overflow."""
    written_val = response.get('reg_value', 0)
    if data > 0xFF:
        expected_data = data & 0xFF
        if written_val != expected_data:
            heatmap_data[byte_addr]["bug_overflow"] += 1
            DETAILS_LOGGER.debug(
                "Ит %d: [BUG FOUND] Overflow Glitch! Записалось %s вместо %s",
                i, hex(written_val), hex(data & 0xFFFF)
            )


def _update_shadow_memory(idx, data, dlab, shadow_memory):
    """Обновление теневой памяти."""
    val_to_store = data & 0xFF
    if data > 0xFF:
        val_to_store = (data ^ 0xDEAD) & 0xFF

    val_to_store_8bit = val_to_store & 0xFF

    if idx == 0 and not dlab:
        pass  # RBR/THR меняются аппаратно
    elif idx in [1, 2] and not dlab:
        pass  # DLL/DLM недоступны без DLAB
    else:
        shadow_memory[idx] = val_to_store_8bit


def _handle_stress_read(i, byte_addr, idx, heatmap_data, shadow_memory, prev_val):
    """Обработка операции чтения внутри стресс-теста."""
    heatmap_data[byte_addr]["reads"] += 1
    response = riscv_br.reg_access(idx, 0, "read")

    if not response.get('ack'):
        if idx <= 9:
            if idx <= 3 or idx == 7:
                heatmap_data[byte_addr]["bug_deadlock"] += 1
                DETAILS_LOGGER.debug("Ит %d:[BUG FOUND] Deadlock", i)
            else:
                heatmap_data[byte_addr]["unexpected_errors"] += 1
                DETAILS_LOGGER.error(
                    "Ит %d: [FAIL] Неожиданный отказ ACK на чтении %s", i, hex(byte_addr)
                )
    else:
        actual_val = response.get('reg_value', 0)
        # Исключаем регистры, которые меняются сами (RBR, LSR)
        # idx=0 проверяем только если FIFO выключен (бит 0 в FCR/Shadow[6] == 0)
        if idx != 7 and idx <= 9 and (idx != 0 or (idx == 0 and not (shadow_memory[6] & 0x01))):
            expected_val = shadow_memory[idx]

            if actual_val != expected_val:
                if prev_val[idx] == actual_val:
                    heatmap_data[byte_addr]["bug_sticky"] += 1
                    DETAILS_LOGGER.debug(
                        "Ит %d: [BUG FOUND] Sticky Bit на %s", i, hex(byte_addr)
                    )
                else:
                    heatmap_data[byte_addr]["mismatches"] += 1
                    DETAILS_LOGGER.error(
                        "Ит %d:[FAIL] Mismatch %s. Ожидалось: %s, Получено: %s",
                        i, hex(byte_addr), hex(expected_val), hex(actual_val)
                    )

        prev_val[idx] = actual_val


def write_final_report(heatmap_data):
    """Генерирует финальный отчет."""
    report_filename = "uart_final_summary.txt"

    # Суммируем ошибки
    stats = {
        "Sticky": sum(r["bug_sticky"] for r in heatmap_data.values()),
        "Deadlock": sum(r["bug_deadlock"] for r in heatmap_data.values()),
        "Overflow": sum(r["bug_overflow"] for r in heatmap_data.values()),
        "Mismatch": sum(r["mismatches"] for r in heatmap_data.values()),
        "Unexpected": sum(r["unexpected_errors"] for r in heatmap_data.values()),
        "RO_Denied": sum(r["ro_denied"] for r in heatmap_data.values())
    }

    with open(report_filename, "w", encoding="utf-8") as f:
        f.write("=" * 120 + "\n")
        f.write("ИТОГОВЫЙ ОТЧЕТ (FINAL_TEST.PY)\n")
        f.write("=" * 120 + "\n\n")

        f.write(f"RO Denied (Success Protection): {stats['RO_Denied']}\n")
        f.write(f"Баг #1 (Sticky):           {stats['Sticky']}\n")
        f.write(f"Баг #2 (Deadlock):         {stats['Deadlock']}\n")
        f.write(f"Баг #3 (Overflow):         {stats['Overflow']}\n")
        f.write(f"Неизвестные Mismatch:      {stats['Mismatch']}\n")
        f.write(f"Неизвестные Ошибки ACK:    {stats['Unexpected']}\n\n")

        f.write("-" * 120 + "\n")
        header = (
            f"{'Адрес':<8} | {'Writes':<8} | {'Reads':<8} | {'RO Denied':<10} | "
            f"{'Sticky':<8} | {'Deadlck':<8} | {'Overflw':<8} | {'Mismtch':<8} | {'Unexp':<8}\n"
        )
        f.write(header)
        f.write("-" * 120 + "\n")

        for addr in sorted(heatmap_data.keys()):
            d = heatmap_data[addr]
            addr_str = f"0x{addr:02X}"
            row = (
                f"{addr_str:<8} | {d['writes']:<8} | {d['reads']:<8} | "
                f"{d['ro_denied']:<10} | {d['bug_sticky']:<8} | {d['bug_deadlock']:<8} | "
                f"{d['bug_overflow']:<8} | {d['mismatches']:<8} | {d['unexpected_errors']:<8}\n"
            )
            f.write(row)

        f.write("-" * 120 + "\n\n")

    DETAILS_LOGGER.info("\n[!] Тест завершен. Отчет: %s", report_filename)


try:
    import pytest

    @pytest.fixture(autouse=True)
    def reset_model():
        """Сбрасывает состояние BlackBox перед каждым тестом (Изоляция тестов)."""
        importlib.reload(riscv_br)

    def test_golden_fsm_tracking_runs_successfully():
        """Интеграционный: Проверяет, что трекинг FSM работает и создает файл."""
        run_fsm_tracking()
        assert os.path.exists("fsm_transitions.json")

    def test_golden_stress_test_runs_successfully():
        """Интеграционный: Запускает фаззинг на коротком числе циклов."""
        run_stress_test(iterations=100)
        assert os.path.exists("uart_final_summary.txt")

    def test_riscv_br_invalid_operation():
        """Покрытие: Недопустимая операция возвращает ack=False."""
        res = riscv_br.reg_access(0, 0, "invalid_op")
        assert not res['ack']

    def test_riscv_br_out_of_bounds_address():
        """Покрытие: Запись/чтение по несуществующему адресу (addr > 9)."""
        res = riscv_br.reg_access(99, 0, "write")
        assert not res['ack']

    def test_riscv_br_read_only_protection():
        """Покрытие: Попытка записи в RO-регистры (IIR=5, LSR=7, MSR=9) блокируется."""
        for addr in [5, 7, 9]:
            res = riscv_br.reg_access(addr, 0xFF, "write")
            assert not res['ack']

    def test_riscv_br_bug1_sticky_bit():
        """Покрытие: Детерминированное воспроизведение Бага #1 (Sticky read)."""
        riscv_br.reg_access(2, 0x42, "write")
        res = riscv_br.reg_access(2, 0, "read")
        assert res['ack']
        assert res['reg_value'] == 0x42

    def test_riscv_br_bug2_deadlock():
        """Покрытие: Детерминированное воспроизведение Бага #2 (Deadlock)."""
        riscv_br.reg_access(3, 0x03, "write")  # Запись в LCR включает флаг lock
        res = riscv_br.reg_access(7, 0, "read")
        assert not res['ack']

    def test_riscv_br_dlab_protection():
        """Покрытие: Защита доступа к регистрам DLL/DLM при DLAB=0."""
        riscv_br.reg_access(3, 0x00, "write")  # DLAB = 0 (уже 0, но явно ставим)
        res = riscv_br.reg_access(1, 0xFF, "write")
        assert res['ack']  # Получаем ACK

        # Значение не должно записаться
        res_read = riscv_br.reg_access(1, 0, "read")
        assert res_read['reg_value'] == 0

    def test_riscv_br_tx_transfer_with_fifo():
        """Покрытие: Корректная работа очереди с включенным FIFO + step_clock()."""
        riscv_br.reg_access(6, 0x01, "write")  # FCR: включаем FIFO
        riscv_br.reg_access(3, 0x00, "write")  # LCR: DLAB = 0

        riscv_br.reg_access(0, 0xAA, "write")  # Пишем в THR (создает event)

        # Проверяем ветку отложенных событий (remaining_events)
        riscv_br.step_clock(0)
        assert len(riscv_br.get_memory_data()) == 0

        # Выполняем событие
        riscv_br.step_clock(2)
        mem = riscv_br.get_memory_data()
        assert len(mem) == 1
        assert mem[0] == (0xAA ^ 0xDEAD) & 0xFF  # С учетом Overflow-глитча модели

    def test_riscv_br_tx_transfer_no_fifo():
        """Покрытие: Прямая передача данных без FIFO и сброс регистра статусов."""
        riscv_br.reg_access(6, 0x00, "write")  # FCR: отключаем FIFO
        riscv_br.reg_access(3, 0x00, "write")  # LCR: DLAB = 0

        riscv_br.reg_access(0, 0xBB, "write")  # Пишем в THR
        riscv_br.step_clock(2)

        res = riscv_br.reg_access(0, 0, "read")  # Читаем из RBR
        assert res['ack']
        assert res['reg_value'] == (0xBB ^ 0xDEAD) & 0xFF

        # Покрытие: Проверяем, что бит DR (Data Ready) сбрасывается при чтении
        lsr_res = riscv_br.reg_access(7, 0, "read")
        assert (lsr_res['reg_value'] & 0x01) == 0

    def test_riscv_br_read_valid_register():
        """Покрытие: Обычное успешное чтение из валидного регистра (например, IER)."""
        res = riscv_br.reg_access(4, 0, "read")
        assert res['ack']
        assert isinstance(res['reg_value'], int)

except ImportError:
    # Защита, если pytest не установлен (код продолжит работать как standalone)
    pass


if __name__ == "__main__":
    # 1. Генерируем граф для дашборда
    run_fsm_tracking()
    print("\n" + "=" * 50)
    # 2. Ищем баги
    run_stress_test(65000)