from typing import Dict, Any

class UARTDevice:
    def __init__(self):
        # Используем индексы (0, 1, 2...) как в вашем REG_MAP
        self._regs = {
            0: 0x00000000, # RBR_THR
            1: 0x00000000, # DLL
            2: 0x00000000, # DLM
            3: 0x00000003, # LCR
            4: 0x00000000, # IER
            5: 0x00000001, # IIR (по умолчанию 1 - нет прерывания)
            6: 0x00000000, # FCR
            7: 0x00000060, # LSR (THRE=1, TEMT=1)
            8: 0x00000000, # MCR
            9: 0x00000000, # MSR
        }
        
    def access(self, addr: int, data: int, operation: str) -> Dict[str, Any]:
        operation = operation.lower()
        
        if addr not in self._regs:
            return {'ack': False, 'reg_value': 0}

        # Логика DLAB теперь смотрит в регистр под индексом 3 (LCR)
        dlab = (self._regs[3] >> 7) & 0x1
        
        if operation == 'read':
            val = self._regs[addr]
            # Если читаем RBR (0) при DLAB=0, сбрасываем Data Ready в LSR (7)
            if addr == 0 and dlab == 0:
                self._regs[7] &= ~0x01
            return {'ack': True, 'reg_value': val}

        elif operation == 'write':
            # Записываем только младшие 8 бит (как в спецификации)
            val_to_write = data & 0xFF
            
            # Если пишем в THR (0) при DLAB=0
            if addr == 0 and dlab == 0:
                self._regs[7] &= ~0x20 # Сбрасываем THRE (занят)
                self._regs[0] = val_to_write
                self._regs[7] |= 0x20  # Возвращаем THRE (освободился)
            else:
                self._regs[addr] = val_to_write
                
            return {'ack': True, 'reg_value': self._regs[addr]}

        return {'ack': False, 'reg_value': 0}

# Инициализация объекта
_uart_hardware = UARTDevice()

def reg_access(addr: int, data: int, operation: str) -> Dict[str, Any]:
    return _uart_hardware.access(addr, data, operation)