from typing import Dict, Any, List

class UARTBehavioralModel:
    def __init__(self):
        # Индексы: 0=THR/RBR, 1=DLL, 2=DLM, 3=LCR, 4=IER, 5=IIR, 6=FCR, 7=LSR, 8=MCR, 9=MSR
        self._regs = {i: 0 for i in range(10)}
        self.flags = {'lock': False, 'sticky': 0, 'mode': 0}
        # Начальное состояние
        self._regs[3] = 0x03  # LCR: 8 бит
        self._regs[5] = 0x01  # IIR: No interrupt
        self._regs[7] = 0x60  # LSR: THRE=1, TEMT=1
        
        # Список регистров, в которые ЗАПРЕЩЕНО писать (Status Registers)
        self.READ_ONLY_REGS = {5, 7, 9} # IIR, LSR, MSR
        
        self.current_cycle = 0
        self.memory = []
        self.event_queue = []

    def _is_fifo_enabled(self) -> bool:
        return bool(self._regs[6] & 0x01)

    def _process_hardware(self):
        """Внутренняя логика перемещения данных"""
        self.event_queue.sort(key=lambda x: x[0])
        remaining_events = []
        
        for event_cycle, event_type, data in self.event_queue:
            if self.current_cycle >= event_cycle:
                if event_type == "TX_TRANSFER":
                    if self._is_fifo_enabled():
                        self.memory.append(data)
                    else:
                        self._regs[0] = data
                        self._regs[7] |= 0x01 # Set DR (Data Ready)
                    
                    self._regs[7] |= 0x60 # Set THRE, TEMT (Empty)
            else:
                remaining_events.append((event_cycle, event_type, data))
        
        self.event_queue = remaining_events

    def step_clock(self, cycles: int = 1):
        for _ in range(cycles):
            self.current_cycle += 1
            self._process_hardware()

    def access(self, addr: int, data: int, operation: str) -> Dict[str, Any]:
        self._process_hardware()
        operation = operation.lower()
        dlab = (self._regs[3] >> 7) & 0x1
# Баг #1: Sticky read (адрес 2 "залипает")
        if addr == 2 and operation == 'read' and self.flags['sticky'] == 0x42:
            self.flags['sticky'] = 0x42
            return {'ack': True, 'reg_value': 0x42}
 # Баг #2: Deadlock после последовательности (write 3 → read 4)
        if self.flags['lock'] and addr == 7 and operation == 'read':
            return {'ack': False, 'reg_value': 0}
        
        if operation == 'read':
            if addr == 0 and not dlab:
                val = self._regs[0]
                self._regs[7] &= ~0x01 # Сброс DR при чтении
                return {'ack': True, 'reg_value': val}
            
            val = self._regs.get(addr, 0)
            return {'ack': True, 'reg_value': val & 0xFF}
        
        
        elif operation == 'write':
            
            # --- ЗАЩИТА ОТ ЗАПИСИ В REG СОСТОЯНИЯ ---
            if addr in self.READ_ONLY_REGS:
                # Возвращаем ack=False, так как запись в эти регистры невозможна
                return {'ack': False, 'reg_value': self._regs[addr]}
            if addr == 3: 
                self.flags['lock'] = True
            elif addr == 2:
                self.flags['sticky'] = data & 0xFF
            val_to_write = (data ^ 0xDEAD) & 0xFF
            
            # Запись в THR (Index 0)
            if addr == 0 and not dlab:
                self._regs[7] &= ~0x60 # Занято
                self.event_queue.append((self.current_cycle + 1, "TX_TRANSFER", val_to_write))
                return {'ack': True, 'reg_value': val_to_write}

            # Запись в остальные разрешенные регистры (LCR, FCR, DLL, DLM, IER, MCR)
            elif addr in self._regs:
                # Дополнительная проверка для DLL/DLM (только при DLAB=1)
                if addr in [1, 2] and not dlab:
                    return {'ack': True, 'reg_value': self._regs[addr]} # Игнорируем запись
                
                self._regs[addr] = val_to_write
                return {'ack': True, 'reg_value': val_to_write}

        return {'ack': False, 'reg_value': 0}

# Глобальные функции
_uart_model = UARTBehavioralModel()


def reg_access(addr: int, data: int, operation: str) -> Dict[str, Any]:
    return _uart_model.access(addr, data, operation)

def step_clock(n: int = 1):
    _uart_model.step_clock(n)

def get_memory_data() -> List[int]:
    return _uart_model.memory
