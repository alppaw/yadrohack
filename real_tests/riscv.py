from typing import Dict, Any, List

class UARTBehavioralModel:
    def __init__(self):
        # Индексы: 0=THR/RBR, 1=DLL, 2=DLM, 3=LCR, 4=IER, 5=IIR, 6=FCR, 7=LSR, 8=MCR, 9=MSR
        self._regs = {i: 0 for i in range(10)}
        
        # Начальное состояние
        self._regs[3] = 0x03  # LCR: WLS=11 (8 бит), DLAB=0
        self._regs[5] = 0x01  # IIR: No interrupt
        self._regs[7] = 0x60  # LSR: THRE=1, TEMT=1
        
        self.READ_ONLY_REGS = {5, 7, 9} # IIR, LSR, MSR
        
        self.current_cycle = 0
        self.memory = []
        self.event_queue = []

    def _get_data_mask(self) -> int:
        """Определяет маску данных на основе битов LCR[1:0] (WLS)"""
        wls = self._regs[3] & 0x03
        masks = {
            0: 0x1F, # 5 бит
            1: 0x3F, # 6 бит
            2: 0x7F, # 7 бит
            3: 0xFF  # 8 бит
        }
        return masks.get(wls, 0xFF)

    def _is_fifo_enabled(self) -> bool:
        return bool(self._regs[6] & 0x01)

    def _process_hardware(self):
        self.event_queue.sort(key=lambda x: x[0])
        remaining_events = []
        
        for event_cycle, event_type, data in self.event_queue:
            if self.current_cycle >= event_cycle:
                if event_type == "TX_TRANSFER":
                    if self._is_fifo_enabled():
                        self.memory.append(data)
                    else:
                        self._regs[0] = data
                        self._regs[7] |= 0x01 # Set DR
                    self._regs[7] |= 0x60 # Set THRE, TEMT
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

        if operation == 'read':
            if addr == 0 and not dlab:
                val = self._regs[0] & self._get_data_mask()
                self._regs[7] &= ~0x01
                return {'ack': True, 'reg_value': val}
            
            val = self._regs.get(addr, 0) & 0xFF
            return {'ack': True, 'reg_value': val}

        elif operation == 'write':
            if addr in self.READ_ONLY_REGS:
                return {'ack': False, 'reg_value': self._regs[addr] & 0xFF}
            
            if addr == 0 and not dlab:
                # ПРИМЕНЯЕМ МАСКУ WLS ПЕРЕД ПЕРЕДАЧЕЙ
                mask = self._get_data_mask()
                val_to_send = data & mask
                
                self._regs[7] &= ~0x60
                self.event_queue.append((self.current_cycle + 1, "TX_TRANSFER", val_to_send))
                return {'ack': True, 'reg_value': val_to_send}

            elif addr in self._regs:
                if addr in [1, 2] and not dlab:
                    return {'ack': True, 'reg_value': self._regs[addr] & 0xFF}
                
                val_to_write = data & 0xFF
                self._regs[addr] = val_to_write
                return {'ack': True, 'reg_value': val_to_write}

        return {'ack': False, 'reg_value': 0}

# Глобальный API
_uart_model = UARTBehavioralModel()

def reg_access(addr: int, data: int, operation: str) -> Dict[str, Any]:
    return _uart_model.access(addr, data, operation)

def step_clock(n: int = 1):
    _uart_model.step_clock(n)

def get_memory_data() -> List[int]:
    return _uart_model.memory