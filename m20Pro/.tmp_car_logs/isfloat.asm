
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000000f5290 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE7IsFloatEv>:
   f5290:	ldrh	w1, [x0, #22]
   f5294:	tbz	w1, #9, f52c0 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE7IsFloatEv+0x30>
   f5298:	ldr	d0, [x0]
   f529c:	adrp	x0, 23b000 <_ZZN9rapidjson8internal5Pow10EiE1e+0x1d0>
   f52a0:	ldr	d1, [x0, #2912]
   f52a4:	fcmpe	d0, d1
   f52a8:	b.lt	f52c0 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE7IsFloatEv+0x30>  // b.tstop
   f52ac:	adrp	x0, 23b000 <_ZZN9rapidjson8internal5Pow10EiE1e+0x1d0>
   f52b0:	ldr	d1, [x0, #2920]
   f52b4:	fcmpe	d0, d1
   f52b8:	cset	w0, ls  // ls = plast
   f52bc:	ret
   f52c0:	mov	w0, #0x0                   	// #0
   f52c4:	ret
