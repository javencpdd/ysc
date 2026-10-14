
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000000d4418 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE>:
   d4418:	sub	sp, sp, #0x4b0
   d441c:	stp	x29, x30, [sp]
   d4420:	mov	x29, sp
   d4424:	stp	x23, x24, [sp, #48]
   d4428:	adrp	x23, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d442c:	add	x24, sp, #0x60
   d4430:	stp	x21, x22, [sp, #32]
   d4434:	mov	x21, x1
   d4438:	adrp	x22, 232000 <_IO_stdin_used+0x3530>
   d443c:	ldr	x1, [x23, #4048]
   d4440:	stp	x19, x20, [sp, #16]
   d4444:	mov	x20, x2
   d4448:	ldr	x2, [x1]
   d444c:	str	x2, [sp, #1192]
   d4450:	mov	x2, #0x0                   	// #0
   d4454:	add	x22, x22, #0xa0
   d4458:	mov	x1, x22
   d445c:	mov	x19, x0
   d4460:	mov	x8, x24
   d4464:	mov	x0, x21
   d4468:	stp	x25, x26, [sp, #64]
   d446c:	mov	x25, x3
   d4470:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d4474:	ldr	w0, [x21]
   d4478:	mov	w3, #0x30                  	// #48
   d447c:	ldr	x2, [x21, #8]
   d4480:	ldr	x1, [sp, #96]
   d4484:	umaddl	x0, w0, w3, x2
   d4488:	cmp	x1, x0
   d448c:	b.eq	d4760 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x348>  // b.none
   d4490:	mov	x1, x22
   d4494:	mov	x0, x21
   d4498:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d449c:	ldr	w22, [x0]
   d44a0:	cmp	w22, #0x3
   d44a4:	b.eq	d4694 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x27c>  // b.none
   d44a8:	str	x27, [sp, #80]
   d44ac:	adrp	x6, 232000 <_IO_stdin_used+0x3530>
   d44b0:	ldr	x27, [x19, #240]
   d44b4:	add	x6, x6, #0xc8
   d44b8:	adrp	x26, 233000 <_IO_stdin_used+0x4530>
   d44bc:	add	x4, x26, #0x248
   d44c0:	mov	x3, #0x400                 	// #1024
   d44c4:	mov	w2, #0x1                   	// #1
   d44c8:	ldr	x5, [x27, #16]
   d44cc:	add	x21, sp, #0xa8
   d44d0:	mov	x1, x3
   d44d4:	mov	x0, x21
   d44d8:	bl	a7f40 <__snprintf_chk@plt>
   d44dc:	mov	x0, x27
   d44e0:	mov	w1, #0x4e20                	// #20000
   d44e4:	bl	a6fb0 <_ZNK9log4cplus6Logger12isEnabledForEi@plt>
   d44e8:	tst	w0, #0xff
   d44ec:	b.eq	d4524 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x10c>  // b.none
   d44f0:	bl	aa660 <_ZN9log4cplus6detail27get_macro_body_snprintf_bufEv@plt>
   d44f4:	mov	w2, w22
   d44f8:	mov	x1, x21
   d44fc:	bl	a7520 <_ZN9log4cplus7helpers12snprintf_buf5printEPKcz@plt>
   d4500:	mov	x2, x0
   d4504:	adrp	x5, 233000 <_IO_stdin_used+0x4530>
   d4508:	adrp	x3, 233000 <_IO_stdin_used+0x4530>
   d450c:	mov	x0, x27
   d4510:	add	x5, x5, #0x570
   d4514:	add	x3, x3, #0x298
   d4518:	mov	w4, #0x8a                  	// #138
   d451c:	mov	w1, #0x4e20                	// #20000
   d4520:	bl	a92c0 <_ZN9log4cplus6detail16macro_forced_logERKNS_6LoggerEiPKcS5_iS5_@plt>
   d4524:	ldr	x0, [x19, #344]
   d4528:	mov	w1, w22
   d452c:	add	x0, x0, #0x110
   d4530:	bl	226078 <_ZN10VelControl19setControlUsageModeENS_16ControlModeParamE>
   d4534:	ldr	x22, [x19, #240]
   d4538:	ldr	x0, [x19, #344]
   d453c:	add	x0, x0, #0x110
   d4540:	bl	224908 <_ZN10VelControl19getControlUsageModeEv>
   d4544:	ldr	x5, [x22, #16]
   d4548:	add	x4, x26, #0x248
   d454c:	adrp	x6, 232000 <_IO_stdin_used+0x3530>
   d4550:	add	x6, x6, #0xe8
   d4554:	mov	x3, #0x400                 	// #1024
   d4558:	mov	w2, #0x1                   	// #1
   d455c:	mov	x1, x3
   d4560:	mov	w26, w0
   d4564:	mov	x0, x21
   d4568:	bl	a7f40 <__snprintf_chk@plt>
   d456c:	mov	x0, x22
   d4570:	mov	w1, #0x4e20                	// #20000
   d4574:	bl	a6fb0 <_ZNK9log4cplus6Logger12isEnabledForEi@plt>
   d4578:	tst	w0, #0xff
   d457c:	b.eq	d45b4 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x19c>  // b.none
   d4580:	bl	aa660 <_ZN9log4cplus6detail27get_macro_body_snprintf_bufEv@plt>
   d4584:	mov	w2, w26
   d4588:	mov	x1, x21
   d458c:	bl	a7520 <_ZN9log4cplus7helpers12snprintf_buf5printEPKcz@plt>
   d4590:	mov	x2, x0
   d4594:	adrp	x5, 232000 <_IO_stdin_used+0x3530>
   d4598:	adrp	x3, 233000 <_IO_stdin_used+0x4530>
   d459c:	mov	x0, x22
   d45a0:	add	x5, x5, #0x100
   d45a4:	add	x3, x3, #0x298
   d45a8:	mov	w4, #0x8a                  	// #138
   d45ac:	mov	w1, #0x4e20                	// #20000
   d45b0:	bl	a92c0 <_ZN9log4cplus6detail16macro_forced_logERKNS_6LoggerEiPKcS5_iS5_@plt>
   d45b4:	add	x22, sp, #0x68
   d45b8:	add	x21, sp, #0x88
   d45bc:	mov	x0, x22
   d45c0:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d45c4:	add	x1, x1, #0xd78
   d45c8:	str	wzr, [sp, #96]
   d45cc:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d45d0:	mov	x2, x24
   d45d4:	mov	x1, x25
   d45d8:	mov	x0, x19
   d45dc:	mov	x3, x22
   d45e0:	mov	x8, x21
   d45e4:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d45e8:	ldp	x1, x2, [sp, #136]
   d45ec:	add	x0, x21, #0x10
   d45f0:	cmp	x1, x0
   d45f4:	ldr	x0, [x20]
   d45f8:	b.eq	d4728 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x310>  // b.none
   d45fc:	stp	x1, x2, [x20]
   d4600:	add	x3, x20, #0x10
   d4604:	cmp	x0, x3
   d4608:	ldr	x3, [sp, #152]
   d460c:	b.eq	d4750 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x338>  // b.none
   d4610:	ldr	x1, [x20, #16]
   d4614:	str	x3, [x20, #16]
   d4618:	cbz	x0, d4754 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x33c>
   d461c:	str	x0, [sp, #136]
   d4620:	str	x1, [sp, #152]
   d4624:	str	xzr, [sp, #144]
   d4628:	add	x21, x21, #0x10
   d462c:	strb	wzr, [x0]
   d4630:	ldr	x0, [sp, #136]
   d4634:	cmp	x0, x21
   d4638:	b.eq	d4640 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x228>  // b.none
   d463c:	bl	a7460 <_ZdlPv@plt>
   d4640:	ldr	x0, [sp, #104]
   d4644:	add	x22, x22, #0x10
   d4648:	cmp	x0, x22
   d464c:	b.eq	d468c <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x274>  // b.none
   d4650:	bl	a7460 <_ZdlPv@plt>
   d4654:	ldr	x27, [sp, #80]
   d4658:	ldr	x23, [x23, #4048]
   d465c:	ldr	x0, [sp, #1192]
   d4660:	ldr	x1, [x23]
   d4664:	subs	x0, x0, x1
   d4668:	mov	x1, #0x0                   	// #0
   d466c:	b.ne	d47b8 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3a0>  // b.any
   d4670:	ldp	x29, x30, [sp]
   d4674:	ldp	x19, x20, [sp, #16]
   d4678:	ldp	x21, x22, [sp, #32]
   d467c:	ldp	x23, x24, [sp, #48]
   d4680:	ldp	x25, x26, [sp, #64]
   d4684:	add	sp, sp, #0x4b0
   d4688:	ret
   d468c:	ldr	x27, [sp, #80]
   d4690:	b	d4658 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x240>
   d4694:	ldr	x0, [x19, #336]
   d4698:	add	x0, x0, #0x8
   d469c:	bl	1c66f8 <_ZN13DeviceControl24supportFollowControlModeEv>
   d46a0:	tst	w0, #0xff
   d46a4:	b.ne	d44a8 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x90>  // b.any
   d46a8:	ldr	x0, [x19, #240]
   d46ac:	adrp	x1, 232000 <_IO_stdin_used+0x3530>
   d46b0:	add	x1, x1, #0xa8
   d46b4:	add	x22, sp, #0x68
   d46b8:	add	x21, sp, #0x88
   d46bc:	bl	f4e00 <_ZN8DrLogger4warnIJEEEvPKcDpOT_>
   d46c0:	mov	w2, #0xe008                	// #57352
   d46c4:	mov	x0, x22
   d46c8:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d46cc:	add	x1, x1, #0xd78
   d46d0:	str	w2, [sp, #96]
   d46d4:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d46d8:	mov	x2, x24
   d46dc:	mov	x1, x25
   d46e0:	mov	x0, x19
   d46e4:	mov	x3, x22
   d46e8:	mov	x8, x21
   d46ec:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d46f0:	mov	x0, x20
   d46f4:	mov	x1, x21
   d46f8:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d46fc:	add	x21, x21, #0x10
   d4700:	ldr	x0, [sp, #136]
   d4704:	cmp	x0, x21
   d4708:	b.eq	d4710 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f8>  // b.none
   d470c:	bl	a7460 <_ZdlPv@plt>
   d4710:	ldr	x0, [sp, #104]
   d4714:	add	x22, x22, #0x10
   d4718:	cmp	x0, x22
   d471c:	b.eq	d4658 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x240>  // b.none
   d4720:	bl	a7460 <_ZdlPv@plt>
   d4724:	b	d4658 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x240>
   d4728:	cbz	x2, d4740 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x328>
   d472c:	cmp	x2, #0x1
   d4730:	b.eq	d47a4 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x38c>  // b.none
   d4734:	bl	a7390 <memcpy@plt>
   d4738:	ldr	x0, [x20]
   d473c:	ldr	x2, [sp, #144]
   d4740:	str	x2, [x20, #8]
   d4744:	strb	wzr, [x0, x2]
   d4748:	ldr	x0, [sp, #136]
   d474c:	b	d4624 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x20c>
   d4750:	str	x3, [x20, #16]
   d4754:	add	x0, x21, #0x10
   d4758:	str	x0, [sp, #136]
   d475c:	b	d4624 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x20c>
   d4760:	mov	w2, #0xe004                	// #57348
   d4764:	add	x22, sp, #0x68
   d4768:	mov	x0, x22
   d476c:	add	x21, sp, #0x88
   d4770:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d4774:	add	x1, x1, #0xd78
   d4778:	str	w2, [sp, #96]
   d477c:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d4780:	mov	x2, x24
   d4784:	mov	x1, x25
   d4788:	mov	x0, x19
   d478c:	mov	x3, x22
   d4790:	mov	x8, x21
   d4794:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d4798:	mov	x1, x21
   d479c:	mov	x0, x20
   d47a0:	b	d46f8 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2e0>
   d47a4:	ldrb	w1, [sp, #152]
   d47a8:	strb	w1, [x0]
   d47ac:	ldr	x0, [x20]
   d47b0:	ldr	x2, [sp, #144]
   d47b4:	b	d4740 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x328>
   d47b8:	str	x27, [sp, #80]
   d47bc:	bl	ab600 <__stack_chk_fail@plt>
   d47c0:	ldr	x1, [sp, #104]
   d47c4:	add	x22, x22, #0x10
   d47c8:	mov	x19, x0
   d47cc:	cmp	x1, x22
   d47d0:	b.eq	d47dc <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3c4>  // b.none
   d47d4:	mov	x0, x1
   d47d8:	bl	a7460 <_ZdlPv@plt>
   d47dc:	mov	x0, x19
   d47e0:	bl	a7a60 <_Unwind_Resume@plt>
   d47e4:	str	x27, [sp, #80]
   d47e8:	b	d47c0 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3a8>
   d47ec:	str	x27, [sp, #80]
   d47f0:	b	d47c0 <_ZN9CmdHandle22cmdHandle_ControlUsageERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3a8>
   d47f4:	nop
