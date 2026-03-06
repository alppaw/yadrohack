"""
Модуль для автогенерации SystemRDL спецификации на основе найденных адресов.
Демонстрирует жюри подход Reverse Engineering -> UVM/RDL Model.
"""

import json
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def generate_rdl(json_file: str = "valid_regs.json", out_rdl: str = "discovered_model.rdl") -> None:
    """Читает JSON с адресами и генерирует SystemRDL файл."""
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            addresses = json.load(f)
    except FileNotFoundError:
        logging.error("Файл %s не найден! Сначала запустите scanner.py", json_file)
        return

    # Шаблон SystemRDL для карты регистров
    rdl_content =[
        "addrmap blackbox_map {",
        '    name = "RISC-V YADRO Blackbox Model";',
        '    desc = "Auto-generated SystemRDL model from valid addresses";',
        "    default regwidth = 32;",
        ""
    ]

    # Шаблон для базового 32-битного регистра RW (чтение/запись)
    reg_template = """    reg {
        name = "Reg_%04X";
        field { sw=rw; hw=rw; } data[31:0] = 32'h0;
    } reg_%04X @ %s;
"""

    for addr in addresses:
        # Для адресов с багами можно добавить комментарии
        hex_addr = f"0x{addr:04X}"
        rdl_content.append(reg_template % (addr, addr, hex_addr))

    rdl_content.append("};")

    with open(out_rdl, "w", encoding="utf-8") as f:
        f.write("\n".join(rdl_content))
        
    logging.info("Успешно сгенерирован SystemRDL файл: %s", out_rdl)
    logging.info("Всего описано регистров: %d", len(addresses))

if __name__ == "__main__":
    generate_rdl()