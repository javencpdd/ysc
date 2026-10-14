
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000000d8be0 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE>:
   d8be0:	sub	sp, sp, #0x4b0
   d8be4:	stp	x29, x30, [sp]
   d8be8:	mov	x29, sp
   d8bec:	stp	x21, x22, [sp, #32]
   d8bf0:	adrp	x22, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d8bf4:	adrp	x21, 232000 <_IO_stdin_used+0x3530>
   d8bf8:	stp	x19, x20, [sp, #16]
   d8bfc:	mov	x19, x1
   d8c00:	mov	x20, x2
   d8c04:	ldr	x1, [x22, #4048]
   d8c08:	add	x21, x21, #0xa58
   d8c0c:	stp	x23, x24, [sp, #48]
   d8c10:	add	x24, sp, #0x60
   d8c14:	ldr	x2, [x1]
   d8c18:	str	x2, [sp, #1192]
   d8c1c:	mov	x2, #0x0                   	// #0
   d8c20:	mov	x23, x0
   d8c24:	mov	x1, x21
   d8c28:	mov	x0, x19
   d8c2c:	mov	x8, x24
   d8c30:	stp	x25, x26, [sp, #64]
   d8c34:	mov	x25, x3
   d8c38:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d8c3c:	ldr	w0, [x19]
   d8c40:	mov	w3, #0x30                  	// #48
   d8c44:	ldr	x2, [x19, #8]
   d8c48:	ldr	x1, [sp, #96]
   d8c4c:	umaddl	x0, w0, w3, x2
   d8c50:	cmp	x1, x0
   d8c54:	b.eq	d8e84 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2a4>  // b.none
   d8c58:	mov	x1, x21
   d8c5c:	mov	x0, x19
   d8c60:	stp	x27, x28, [sp, #80]
   d8c64:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d8c68:	ldrh	w26, [x0, #22]
   d8c6c:	ldr	x21, [x23, #240]
   d8c70:	cmp	w26, #0xa
   d8c74:	adrp	x6, 232000 <_IO_stdin_used+0x3530>
   d8c78:	adrp	x4, 233000 <_IO_stdin_used+0x4530>
   d8c7c:	add	x6, x6, #0xa60
   d8c80:	add	x4, x4, #0x248
   d8c84:	ldr	x5, [x21, #16]
   d8c88:	mov	x3, #0x400                 	// #1024
   d8c8c:	mov	w2, #0x1                   	// #1
   d8c90:	add	x27, sp, #0xa8
   d8c94:	cset	w28, eq  // eq = none
   d8c98:	mov	x1, x3
   d8c9c:	mov	x0, x27
   d8ca0:	bl	a7f40 <__snprintf_chk@plt>
   d8ca4:	mov	x0, x21
   d8ca8:	mov	w1, #0x4e20                	// #20000
   d8cac:	bl	a6fb0 <_ZNK9log4cplus6Logger12isEnabledForEi@plt>
   d8cb0:	tst	w0, #0xff
   d8cb4:	b.eq	d8cec <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x10c>  // b.none
   d8cb8:	bl	aa660 <_ZN9log4cplus6detail27get_macro_body_snprintf_bufEv@plt>
   d8cbc:	mov	w2, w28
   d8cc0:	mov	x1, x27
   d8cc4:	bl	a7520 <_ZN9log4cplus7helpers12snprintf_buf5printEPKcz@plt>
   d8cc8:	mov	x2, x0
   d8ccc:	adrp	x5, 232000 <_IO_stdin_used+0x3530>
   d8cd0:	adrp	x3, 233000 <_IO_stdin_used+0x4530>
   d8cd4:	mov	x0, x21
   d8cd8:	add	x5, x5, #0xa80
   d8cdc:	add	x3, x3, #0x298
   d8ce0:	mov	w4, #0x8a                  	// #138
   d8ce4:	mov	w1, #0x4e20                	// #20000
   d8ce8:	bl	a92c0 <_ZN9log4cplus6detail16macro_forced_logERKNS_6LoggerEiPKcS5_iS5_@plt>
   d8cec:	cmp	w26, #0xa
   d8cf0:	b.eq	d8de8 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x208>  // b.none
   d8cf4:	adrp	x21, 2d4000 <_ZZN9SingletonI15ExceptionHandleE11getInstanceEvE8instance+0x350>
   d8cf8:	add	x0, x21, #0xbb8
   d8cfc:	ldarb	w1, [x0]
   d8d00:	adrp	x19, 2d4000 <_ZZN9SingletonI15ExceptionHandleE11getInstanceEvE8instance+0x350>
   d8d04:	tbz	w1, #0, d8f38 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x358>
   d8d08:	add	x0, x19, #0xbc0
   d8d0c:	mov	w1, #0x0                   	// #0
   d8d10:	bl	1bad10 <_ZN9DDSWorker9SDKEnableEj>
   d8d14:	add	x21, sp, #0x68
   d8d18:	add	x19, sp, #0x88
   d8d1c:	add	x4, x21, #0x10
   d8d20:	mov	x2, x24
   d8d24:	mov	x1, x25
   d8d28:	mov	x0, x23
   d8d2c:	mov	x3, x21
   d8d30:	mov	x8, x19
   d8d34:	str	wzr, [sp, #96]
   d8d38:	stp	x4, xzr, [sp, #104]
   d8d3c:	strb	wzr, [sp, #120]
   d8d40:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d8d44:	ldp	x1, x2, [sp, #136]
   d8d48:	add	x0, x19, #0x10
   d8d4c:	cmp	x1, x0
   d8d50:	ldr	x0, [x20]
   d8d54:	b.eq	d8e5c <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x27c>  // b.none
   d8d58:	stp	x1, x2, [x20]
   d8d5c:	add	x3, x20, #0x10
   d8d60:	cmp	x0, x3
   d8d64:	ldr	x3, [sp, #152]
   d8d68:	b.eq	d8ef4 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x314>  // b.none
   d8d6c:	ldr	x1, [x20, #16]
   d8d70:	str	x3, [x20, #16]
   d8d74:	cbz	x0, d8ef8 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x318>
   d8d78:	str	x0, [sp, #136]
   d8d7c:	str	x1, [sp, #152]
   d8d80:	str	xzr, [sp, #144]
   d8d84:	add	x19, x19, #0x10
   d8d88:	strb	wzr, [x0]
   d8d8c:	ldr	x0, [sp, #136]
   d8d90:	cmp	x0, x19
   d8d94:	b.eq	d8d9c <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1bc>  // b.none
   d8d98:	bl	a7460 <_ZdlPv@plt>
   d8d9c:	ldr	x0, [sp, #104]
   d8da0:	add	x21, x21, #0x10
   d8da4:	cmp	x0, x21
   d8da8:	b.eq	d8e54 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x274>  // b.none
   d8dac:	bl	a7460 <_ZdlPv@plt>
   d8db0:	ldp	x27, x28, [sp, #80]
   d8db4:	ldr	x0, [x22, #4048]
   d8db8:	ldr	x1, [sp, #1192]
   d8dbc:	ldr	x2, [x0]
   d8dc0:	subs	x1, x1, x2
   d8dc4:	mov	x2, #0x0                   	// #0
   d8dc8:	b.ne	d8f80 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3a0>  // b.any
   d8dcc:	ldp	x29, x30, [sp]
   d8dd0:	ldp	x19, x20, [sp, #16]
   d8dd4:	ldp	x21, x22, [sp, #32]
   d8dd8:	ldp	x23, x24, [sp, #48]
   d8ddc:	ldp	x25, x26, [sp, #64]
   d8de0:	add	sp, sp, #0x4b0
   d8de4:	ret
   d8de8:	adrp	x21, 232000 <_IO_stdin_used+0x3530>
   d8dec:	add	x21, x21, #0xac8
   d8df0:	mov	x1, x21
   d8df4:	mov	x0, x19
   d8df8:	mov	x8, x24
   d8dfc:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d8e00:	ldr	w0, [x19]
   d8e04:	mov	w3, #0x30                  	// #48
   d8e08:	ldr	x2, [x19, #8]
   d8e0c:	mov	w26, #0xc8                  	// #200
   d8e10:	ldr	x1, [sp, #96]
   d8e14:	umaddl	x0, w0, w3, x2
   d8e18:	cmp	x1, x0
   d8e1c:	b.eq	d8e30 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x250>  // b.none
   d8e20:	mov	x1, x21
   d8e24:	mov	x0, x19
   d8e28:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d8e2c:	ldr	w26, [x0]
   d8e30:	adrp	x21, 2d4000 <_ZZN9SingletonI15ExceptionHandleE11getInstanceEvE8instance+0x350>
   d8e34:	add	x0, x21, #0xbb8
   d8e38:	ldarb	w1, [x0]
   d8e3c:	adrp	x19, 2d4000 <_ZZN9SingletonI15ExceptionHandleE11getInstanceEvE8instance+0x350>
   d8e40:	tbz	w1, #0, d8f04 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x324>
   d8e44:	mov	w1, w26
   d8e48:	add	x0, x19, #0xbc0
   d8e4c:	bl	1bad10 <_ZN9DDSWorker9SDKEnableEj>
   d8e50:	b	d8d14 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x134>
   d8e54:	ldp	x27, x28, [sp, #80]
   d8e58:	b	d8db4 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1d4>
   d8e5c:	cbz	x2, d8e74 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x294>
   d8e60:	cmp	x2, #0x1
   d8e64:	b.eq	d8f6c <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x38c>  // b.none
   d8e68:	bl	a7390 <memcpy@plt>
   d8e6c:	ldr	x0, [x20]
   d8e70:	ldr	x2, [sp, #144]
   d8e74:	str	x2, [x20, #8]
   d8e78:	strb	wzr, [x0, x2]
   d8e7c:	ldr	x0, [sp, #136]
   d8e80:	b	d8d80 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1a0>
   d8e84:	mov	w2, #0xe004                	// #57348
   d8e88:	add	x21, sp, #0x68
   d8e8c:	mov	x0, x21
   d8e90:	add	x19, sp, #0x88
   d8e94:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d8e98:	add	x1, x1, #0xd78
   d8e9c:	str	w2, [sp, #96]
   d8ea0:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d8ea4:	mov	x2, x24
   d8ea8:	mov	x1, x25
   d8eac:	mov	x0, x23
   d8eb0:	mov	x3, x21
   d8eb4:	mov	x8, x19
   d8eb8:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d8ebc:	mov	x1, x19
   d8ec0:	mov	x0, x20
   d8ec4:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d8ec8:	add	x19, x19, #0x10
   d8ecc:	ldr	x0, [sp, #136]
   d8ed0:	cmp	x0, x19
   d8ed4:	b.eq	d8edc <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2fc>  // b.none
   d8ed8:	bl	a7460 <_ZdlPv@plt>
   d8edc:	ldr	x0, [sp, #104]
   d8ee0:	add	x21, x21, #0x10
   d8ee4:	cmp	x0, x21
   d8ee8:	b.eq	d8db4 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1d4>  // b.none
   d8eec:	bl	a7460 <_ZdlPv@plt>
   d8ef0:	b	d8db4 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1d4>
   d8ef4:	str	x3, [x20, #16]
   d8ef8:	add	x0, x19, #0x10
   d8efc:	str	x0, [sp, #136]
   d8f00:	b	d8d80 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1a0>
   d8f04:	bl	a99b0 <__cxa_guard_acquire@plt>
   d8f08:	cbz	w0, d8e44 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x264>
   d8f0c:	add	x0, x19, #0xbc0
   d8f10:	bl	ff400 <_ZN9DDSWorkerC1Ev>
   d8f14:	add	x1, x19, #0xbc0
   d8f18:	adrp	x2, 2d3000 <__data_start>
   d8f1c:	add	x2, x2, #0x8
   d8f20:	adrp	x0, fe000 <_ZN4toml4findIbNS_16discard_commentsESt13unordered_mapSt6vectorRA13_KcS6_JEEEDTcl3getIT_Ecl7declvalIRNS_11basic_valueIT0_T1_T2_EEEEEESD_OT3_OT4_DpOT5_+0x138>
   d8f24:	add	x0, x0, #0xa40
   d8f28:	bl	aa9d0 <__cxa_atexit@plt>
   d8f2c:	add	x0, x21, #0xbb8
   d8f30:	bl	aa0a0 <__cxa_guard_release@plt>
   d8f34:	b	d8e44 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x264>
   d8f38:	bl	a99b0 <__cxa_guard_acquire@plt>
   d8f3c:	cbz	w0, d8d08 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x128>
   d8f40:	add	x0, x19, #0xbc0
   d8f44:	bl	ff400 <_ZN9DDSWorkerC1Ev>
   d8f48:	add	x1, x19, #0xbc0
   d8f4c:	adrp	x2, 2d3000 <__data_start>
   d8f50:	add	x2, x2, #0x8
   d8f54:	adrp	x0, fe000 <_ZN4toml4findIbNS_16discard_commentsESt13unordered_mapSt6vectorRA13_KcS6_JEEEDTcl3getIT_Ecl7declvalIRNS_11basic_valueIT0_T1_T2_EEEEEESD_OT3_OT4_DpOT5_+0x138>
   d8f58:	add	x0, x0, #0xa40
   d8f5c:	bl	aa9d0 <__cxa_atexit@plt>
   d8f60:	add	x0, x21, #0xbb8
   d8f64:	bl	aa0a0 <__cxa_guard_release@plt>
   d8f68:	b	d8d08 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x128>
   d8f6c:	ldrb	w1, [sp, #152]
   d8f70:	strb	w1, [x0]
   d8f74:	ldr	x0, [x20]
   d8f78:	ldr	x2, [sp, #144]
   d8f7c:	b	d8e74 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x294>
   d8f80:	stp	x27, x28, [sp, #80]
   d8f84:	bl	ab600 <__stack_chk_fail@plt>
   d8f88:	mov	x19, x0
   d8f8c:	add	x0, x21, #0xbb8
   d8f90:	bl	a70e0 <__cxa_guard_abort@plt>
   d8f94:	mov	x0, x19
   d8f98:	bl	a7a60 <_Unwind_Resume@plt>
   d8f9c:	ldr	x1, [sp, #104]
   d8fa0:	add	x21, x21, #0x10
   d8fa4:	mov	x19, x0
   d8fa8:	cmp	x1, x21
   d8fac:	b.eq	d8f94 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3b4>  // b.none
   d8fb0:	mov	x0, x1
   d8fb4:	bl	a7460 <_ZdlPv@plt>
   d8fb8:	b	d8f94 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3b4>
   d8fbc:	stp	x27, x28, [sp, #80]
   d8fc0:	b	d8f9c <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3bc>
   d8fc4:	b	d8f88 <_ZN9CmdHandle19cmdHandle_EnableSDKERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3a8>
