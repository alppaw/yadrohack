# uart_blackbox.py - НЕ РЕДАКТИРОВАТЬ
from typing import Dict, Any
import random

class UARTBlackBox:
    def __init__(self):
        self.state = [0] * 16
        self.flags = {'lock': False, 'sticky': 0, 'mode': 0}
        
    def reg_access(self, addr: int, data: int, operation: str) -> Dict[str, Any]:
        if addr < 0 or addr > 15:
            return {'ack': False, 'reg_value': 0}
            
        op = operation.lower()
        
        # Баг #1: Sticky read (адрес 2 "залипает")
        if addr == 2 and op == 'read' and self.flags['sticky'] == 0x42:
            self.flags['sticky'] = 0x42
            return {'ack': True, 'reg_value': 0x42}
        
        # Баг #2: Deadlock после последовательности (write 3 → read 4)
        if self.flags['lock'] and addr == 4 and op == 'read':
            return {'ack': False, 'reg_value': 0}
        
        # Баг #3: Overflow glitch (data > 0xFFFF)
        if data > 0xFFFF:
            data = (data ^ 0xDEAD) & 0xFFFF
        
        if op == 'write':
            self.state[addr] = data & 0xFFFF
            # Состояние багов
            if addr == 3: 
                self.flags['lock'] = True
            elif addr == 2:
                self.flags['sticky'] = data & 0xFF
            return {'ack': True, 'reg_value': data & 0xFFFF}
            
        elif op == 'read':
            return {'ack': True, 'reg_value': self.state[addr]}
        
        return {'ack': False, 'reg_value': 0}

uart = UARTBlackBox()
def reg_access(addr: int, data: int, operation: str) -> Dict[str, Any]:
    return uart.reg_access(addr, data, operation)
