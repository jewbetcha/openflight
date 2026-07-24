# Rev C ADC Production Release Plan

1. Encode the RF cable, connector MPNs, pin maps, DNP rules, and copper-layer
   order in a machine-checkable interface contract.
2. Update the schematic and PCB so all RF control lines reach Raspberry Pi
   GPIOs, enable lines default low, and J2 is a bottom-mounted female socket.
3. Generate the PCBWay BOM, CPL, schematic, assembly drawings, fabrication
   notes, cable/system BOM, and board README.
4. Run interface tests, ERC, DRC, schematic/PCB analysis, Gerber export, and
   Gerber validation from the final sources.
5. Create one PCBWay upload ZIP and report every copper layer name and order.
