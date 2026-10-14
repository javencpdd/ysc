
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000000d2430 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE>:
   d2430:	stp	x29, x30, [sp, #-240]!
   d2434:	mov	x29, sp
   d2438:	stp	x21, x22, [sp, #32]
   d243c:	adrp	x21, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d2440:	adrp	x22, 24d000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM15ExceptionHandleFvvEPS3_EEEEEE+0x4e0>
   d2444:	stp	x19, x20, [sp, #16]
   d2448:	mov	x19, x1
   d244c:	add	x20, sp, #0x80
   d2450:	ldr	x1, [x21, #4048]
   d2454:	stp	x25, x26, [sp, #64]
   d2458:	mov	x26, x2
   d245c:	ldr	x2, [x1]
   d2460:	str	x2, [sp, #232]
   d2464:	mov	x2, #0x0                   	// #0
   d2468:	add	x22, x22, #0x8e8
   d246c:	mov	x1, x22
   d2470:	mov	x25, x0
   d2474:	mov	x8, x20
   d2478:	mov	x0, x19
   d247c:	stp	x23, x24, [sp, #48]
   d2480:	mov	x24, x3
   d2484:	mov	w23, #0x30                  	// #48
   d2488:	str	d8, [sp, #96]
   d248c:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2490:	ldr	w0, [x19]
   d2494:	ldr	x2, [x19, #8]
   d2498:	ldr	x1, [sp, #128]
   d249c:	umaddl	x0, w0, w23, x2
   d24a0:	cmp	x1, x0
   d24a4:	b.eq	d2768 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x338>  // b.none
   d24a8:	mov	x0, x19
   d24ac:	mov	x8, x20
   d24b0:	stp	x27, x28, [sp, #80]
   d24b4:	adrp	x27, 24d000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM15ExceptionHandleFvvEPS3_EEEEEE+0x4e0>
   d24b8:	add	x1, x27, #0xb18
   d24bc:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d24c0:	ldr	w0, [x19]
   d24c4:	ldr	x2, [x19, #8]
   d24c8:	ldr	x1, [sp, #128]
   d24cc:	umaddl	x0, w0, w23, x2
   d24d0:	cmp	x1, x0
   d24d4:	b.eq	d2764 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d24d8:	mov	x0, x19
   d24dc:	mov	x8, x20
   d24e0:	adrp	x28, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
   d24e4:	add	x1, x28, #0xbe8
   d24e8:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d24ec:	ldr	w0, [x19]
   d24f0:	ldr	x2, [x19, #8]
   d24f4:	ldr	x1, [sp, #128]
   d24f8:	umaddl	x0, w0, w23, x2
   d24fc:	cmp	x1, x0
   d2500:	b.eq	d2764 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2504:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2508:	mov	x8, x20
   d250c:	add	x1, x0, #0xb50
   d2510:	mov	x0, x19
   d2514:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2518:	ldr	w0, [x19]
   d251c:	ldr	x2, [x19, #8]
   d2520:	ldr	x1, [sp, #128]
   d2524:	umaddl	x0, w0, w23, x2
   d2528:	cmp	x1, x0
   d252c:	b.eq	d2764 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2530:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2534:	mov	x8, x20
   d2538:	add	x1, x0, #0xb58
   d253c:	mov	x0, x19
   d2540:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2544:	ldr	w0, [x19]
   d2548:	ldr	x2, [x19, #8]
   d254c:	ldr	x1, [sp, #128]
   d2550:	umaddl	x0, w0, w23, x2
   d2554:	cmp	x1, x0
   d2558:	b.eq	d2764 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d255c:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2560:	mov	x8, x20
   d2564:	add	x1, x0, #0xb60
   d2568:	mov	x0, x19
   d256c:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2570:	ldr	w0, [x19]
   d2574:	ldr	x2, [x19, #8]
   d2578:	ldr	x1, [sp, #128]
   d257c:	umaddl	x23, w0, w23, x2
   d2580:	cmp	x1, x23
   d2584:	b.eq	d2764 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2588:	mov	x0, x20
   d258c:	bl	aa2f0 <_ZN5drdds3msg5SteerC1Ev@plt>
   d2590:	mov	x1, x22
   d2594:	mov	x0, x19
   d2598:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d259c:	bl	f5290 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE7IsFloatEv>
   d25a0:	tst	w0, #0xff
   d25a4:	b.eq	d27d8 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3a8>  // b.none
   d25a8:	mov	x1, x22
   d25ac:	mov	x0, x19
   d25b0:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d25b4:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d25b8:	fcvt	s8, d0
   d25bc:	mov	x0, x20
   d25c0:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d25c4:	bl	aa010 <_ZN5drdds3msg10SteerValue1xEv@plt>
   d25c8:	mov	x2, x0
   d25cc:	add	x1, x27, #0xb18
   d25d0:	mov	x0, x19
   d25d4:	str	s8, [x2]
   d25d8:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d25dc:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d25e0:	fcvt	s8, d0
   d25e4:	mov	x0, x20
   d25e8:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d25ec:	bl	a8d40 <_ZN5drdds3msg10SteerValue1yEv@plt>
   d25f0:	mov	x2, x0
   d25f4:	add	x1, x28, #0xbe8
   d25f8:	mov	x0, x19
   d25fc:	str	s8, [x2]
   d2600:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2604:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2608:	fcvt	s8, d0
   d260c:	mov	x0, x20
   d2610:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2614:	bl	a8150 <_ZN5drdds3msg10SteerValue1zEv@plt>
   d2618:	mov	x2, x0
   d261c:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2620:	add	x1, x0, #0xb50
   d2624:	mov	x0, x19
   d2628:	str	s8, [x2]
   d262c:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2630:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2634:	fcvt	s8, d0
   d2638:	mov	x0, x20
   d263c:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2640:	bl	ab0c0 <_ZN5drdds3msg10SteerValue4rollEv@plt>
   d2644:	mov	x2, x0
   d2648:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d264c:	add	x1, x0, #0xb58
   d2650:	mov	x0, x19
   d2654:	str	s8, [x2]
   d2658:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d265c:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2660:	fcvt	s8, d0
   d2664:	mov	x0, x20
   d2668:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d266c:	bl	a8650 <_ZN5drdds3msg10SteerValue5pitchEv@plt>
   d2670:	mov	x2, x0
   d2674:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2678:	add	x1, x0, #0xb60
   d267c:	mov	x0, x19
   d2680:	str	s8, [x2]
   d2684:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2688:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d268c:	fcvt	s8, d0
   d2690:	mov	x0, x20
   d2694:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2698:	bl	aab30 <_ZN5drdds3msg10SteerValue3yawEv@plt>
   d269c:	str	s8, [x0]
   d26a0:	adrp	x19, 2d3000 <__data_start>
   d26a4:	add	x22, x19, #0x478
   d26a8:	add	x0, x22, #0x7c8
   d26ac:	ldarb	w1, [x0]
   d26b0:	tbnz	w1, #0, d26bc <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x28c>
   d26b4:	bl	a99b0 <__cxa_guard_acquire@plt>
   d26b8:	cbnz	w0, d287c <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x44c>
   d26bc:	bl	aa6e0 <_ZNSt6chrono3_V212system_clock3nowEv@plt>
   d26c0:	mov	x1, #0x94b3                	// #38067
   d26c4:	add	x3, x19, #0x478
   d26c8:	movk	x1, #0x26d6, lsl #16
   d26cc:	movk	x1, #0xbe8, lsl #32
   d26d0:	movk	x1, #0x112e, lsl #48
   d26d4:	ldr	x4, [x24, #8]
   d26d8:	smulh	x1, x0, x1
   d26dc:	ldr	x2, [x3, #2008]
   d26e0:	asr	x1, x1, #26
   d26e4:	sub	x22, x1, x0, asr #63
   d26e8:	cmp	x2, x4
   d26ec:	b.eq	d28b0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x480>  // b.none
   d26f0:	add	x28, x19, #0x478
   d26f4:	adrp	x23, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d26f8:	add	x27, x28, #0x7d0
   d26fc:	add	x1, x23, #0xd78
   d2700:	mov	x0, x27
   d2704:	bl	aaf10 <_ZNKSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEE7compareEPKc@plt>
   d2708:	cbnz	w0, d285c <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x42c>
   d270c:	add	x19, x19, #0x478
   d2710:	mov	x1, x20
   d2714:	ldr	x0, [x25, #344]
   d2718:	str	x22, [x19, #2032]
   d271c:	add	x0, x0, #0x110
   d2720:	bl	225210 <_ZN10VelControl7sendVelERN5drdds3msg5SteerE>
   d2724:	mov	x0, x20
   d2728:	bl	a8a00 <_ZN5drdds3msg5SteerD1Ev@plt>
   d272c:	ldp	x27, x28, [sp, #80]
   d2730:	ldr	x21, [x21, #4048]
   d2734:	ldr	x0, [sp, #232]
   d2738:	ldr	x1, [x21]
   d273c:	subs	x0, x0, x1
   d2740:	mov	x1, #0x0                   	// #0
   d2744:	b.ne	d29c4 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x594>  // b.any
   d2748:	ldp	x19, x20, [sp, #16]
   d274c:	ldp	x21, x22, [sp, #32]
   d2750:	ldp	x23, x24, [sp, #48]
   d2754:	ldp	x25, x26, [sp, #64]
   d2758:	ldr	d8, [sp, #96]
   d275c:	ldp	x29, x30, [sp], #240
   d2760:	ret
   d2764:	ldp	x27, x28, [sp, #80]
   d2768:	mov	w2, #0xe004                	// #57348
   d276c:	add	x19, sp, #0xa8
   d2770:	add	x22, sp, #0xc8
   d2774:	mov	x0, x19
   d2778:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d277c:	add	x1, x1, #0xd78
   d2780:	str	w2, [sp, #128]
   d2784:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d2788:	mov	x2, x20
   d278c:	mov	x1, x24
   d2790:	mov	x0, x25
   d2794:	mov	x3, x19
   d2798:	mov	x8, x22
   d279c:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d27a0:	mov	x1, x22
   d27a4:	mov	x0, x26
   d27a8:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d27ac:	add	x22, x22, #0x10
   d27b0:	ldr	x0, [sp, #200]
   d27b4:	cmp	x0, x22
   d27b8:	b.eq	d27c0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x390>  // b.none
   d27bc:	bl	a7460 <_ZdlPv@plt>
   d27c0:	ldr	x0, [sp, #168]
   d27c4:	add	x19, x19, #0x10
   d27c8:	cmp	x0, x19
   d27cc:	b.eq	d2730 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x300>  // b.none
   d27d0:	bl	a7460 <_ZdlPv@plt>
   d27d4:	b	d2730 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x300>
   d27d8:	mov	x1, x22
   d27dc:	mov	x0, x19
   d27e0:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d27e4:	ldrh	w0, [x0, #22]
   d27e8:	tbz	w0, #10, d26a0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x270>
   d27ec:	mov	w2, #0xe005                	// #57349
   d27f0:	add	x22, sp, #0xc8
   d27f4:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d27f8:	mov	x0, x22
   d27fc:	add	x1, x1, #0xd78
   d2800:	str	w2, [sp, #120]
   d2804:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d2808:	add	x19, sp, #0xa8
   d280c:	mov	x1, x24
   d2810:	mov	x0, x25
   d2814:	mov	x8, x19
   d2818:	mov	x3, x22
   d281c:	add	x2, sp, #0x78
   d2820:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d2824:	mov	x1, x19
   d2828:	mov	x0, x26
   d282c:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d2830:	add	x19, x19, #0x10
   d2834:	ldr	x0, [sp, #168]
   d2838:	cmp	x0, x19
   d283c:	b.eq	d2844 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x414>  // b.none
   d2840:	bl	a7460 <_ZdlPv@plt>
   d2844:	ldr	x0, [sp, #200]
   d2848:	add	x22, x22, #0x10
   d284c:	cmp	x0, x22
   d2850:	b.eq	d2724 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>  // b.none
   d2854:	bl	a7460 <_ZdlPv@plt>
   d2858:	b	d2724 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>
   d285c:	ldr	x0, [x28, #2032]
   d2860:	sub	x0, x22, x0
   d2864:	cmp	x0, #0x2
   d2868:	b.le	d28c8 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x498>
   d286c:	mov	x1, x24
   d2870:	mov	x0, x27
   d2874:	bl	a8ea0 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEE9_M_assignERKS4_@plt>
   d2878:	b	d270c <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2dc>
   d287c:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d2880:	add	x0, x22, #0x7d0
   d2884:	add	x1, x1, #0xd78
   d2888:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d288c:	adrp	x0, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d2890:	add	x1, x22, #0x7d0
   d2894:	adrp	x2, 2d3000 <__data_start>
   d2898:	add	x2, x2, #0x8
   d289c:	ldr	x0, [x0, #3992]
   d28a0:	bl	aa9d0 <__cxa_atexit@plt>
   d28a4:	add	x0, x22, #0x7c8
   d28a8:	bl	aa0a0 <__cxa_guard_release@plt>
   d28ac:	b	d26bc <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x28c>
   d28b0:	cbz	x2, d270c <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2dc>
   d28b4:	ldr	x1, [x24]
   d28b8:	ldr	x0, [x3, #2000]
   d28bc:	bl	a8bf0 <memcmp@plt>
   d28c0:	cbz	w0, d270c <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2dc>
   d28c4:	b	d26f0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2c0>
   d28c8:	ldr	x5, [x24]
   d28cc:	add	x27, sp, #0x78
   d28d0:	ldr	x0, [x25, #240]
   d28d4:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d28d8:	ldr	x4, [x28, #2000]
   d28dc:	mov	x3, x27
   d28e0:	add	x2, sp, #0x70
   d28e4:	add	x1, x1, #0xe08
   d28e8:	stp	x5, x4, [sp, #112]
   d28ec:	bl	f52c8 <_ZN8DrLogger4infoIJPKcS2_EEEvS2_DpOT_>
   d28f0:	adrp	x22, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d28f4:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d28f8:	mov	x2, #0x4                   	// #4
   d28fc:	add	x1, x1, #0xe38
   d2900:	ldr	x0, [x22, #3680]
   d2904:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2908:	ldp	x1, x2, [x24]
   d290c:	ldr	x0, [x22, #3680]
   d2910:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2914:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d2918:	mov	x22, x0
   d291c:	add	x1, x1, #0xe40
   d2920:	mov	x2, #0x19                  	// #25
   d2924:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2928:	add	x19, x19, #0x478
   d292c:	mov	x0, x22
   d2930:	ldr	x1, [x19, #2000]
   d2934:	ldr	x2, [x19, #2008]
   d2938:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d293c:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d2940:	mov	x19, x0
   d2944:	add	x1, x1, #0xe60
   d2948:	mov	x2, #0xa                   	// #10
   d294c:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2950:	mov	x0, x19
   d2954:	bl	a8a10 <_ZSt4endlIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_@plt>
   d2958:	mov	w2, #0xe006                	// #57350
   d295c:	add	x19, sp, #0xa8
   d2960:	add	x1, x23, #0xd78
   d2964:	mov	x0, x19
   d2968:	str	w2, [sp, #120]
   d296c:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d2970:	add	x22, sp, #0xc8
   d2974:	mov	x2, x27
   d2978:	mov	x1, x24
   d297c:	mov	x0, x25
   d2980:	mov	x8, x22
   d2984:	mov	x3, x19
   d2988:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d298c:	mov	x1, x22
   d2990:	mov	x0, x26
   d2994:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d2998:	add	x22, x22, #0x10
   d299c:	ldr	x0, [sp, #200]
   d29a0:	cmp	x0, x22
   d29a4:	b.eq	d29ac <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x57c>  // b.none
   d29a8:	bl	a7460 <_ZdlPv@plt>
   d29ac:	ldr	x0, [sp, #168]
   d29b0:	add	x19, x19, #0x10
   d29b4:	cmp	x0, x19
   d29b8:	b.eq	d2724 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>  // b.none
   d29bc:	bl	a7460 <_ZdlPv@plt>
   d29c0:	b	d2724 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>
   d29c4:	stp	x27, x28, [sp, #80]
   d29c8:	bl	ab600 <__stack_chk_fail@plt>
   d29cc:	mov	x1, x0
   d29d0:	add	x19, x19, #0x478
   d29d4:	add	x0, x19, #0x7c8
   d29d8:	mov	x19, x1
   d29dc:	bl	a70e0 <__cxa_guard_abort@plt>
   d29e0:	mov	x0, x20
   d29e4:	bl	a8a00 <_ZN5drdds3msg5SteerD1Ev@plt>
   d29e8:	mov	x0, x19
   d29ec:	bl	a7a60 <_Unwind_Resume@plt>
   d29f0:	ldr	x1, [sp, #168]
   d29f4:	add	x19, x19, #0x10
   d29f8:	mov	x21, x0
   d29fc:	cmp	x1, x19
   d2a00:	b.eq	d2a0c <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5dc>  // b.none
   d2a04:	mov	x0, x1
   d2a08:	bl	a7460 <_ZdlPv@plt>
   d2a0c:	mov	x19, x21
   d2a10:	b	d29e0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5b0>
   d2a14:	ldr	x1, [sp, #200]
   d2a18:	add	x22, x22, #0x10
   d2a1c:	mov	x19, x0
   d2a20:	cmp	x1, x22
   d2a24:	b.eq	d29e0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5b0>  // b.none
   d2a28:	mov	x0, x1
   d2a2c:	bl	a7460 <_ZdlPv@plt>
   d2a30:	b	d29e0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5b0>
   d2a34:	mov	x19, x0
   d2a38:	b	d29e0 <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5b0>
   d2a3c:	ldr	x1, [sp, #168]
   d2a40:	stp	x27, x28, [sp, #80]
   d2a44:	add	x19, x19, #0x10
   d2a48:	mov	x20, x0
   d2a4c:	cmp	x1, x19
   d2a50:	b.eq	d2a5c <_ZN9CmdHandle15cmdHandle_SteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x62c>  // b.none
   d2a54:	mov	x0, x1
   d2a58:	bl	a7460 <_ZdlPv@plt>
   d2a5c:	mov	x0, x20
   d2a60:	bl	a7a60 <_Unwind_Resume@plt>
   d2a64:	nop

00000000000d2a68 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE>:
   d2a68:	stp	x29, x30, [sp, #-240]!
   d2a6c:	mov	x29, sp
   d2a70:	stp	x21, x22, [sp, #32]
   d2a74:	adrp	x21, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d2a78:	adrp	x22, 24d000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM15ExceptionHandleFvvEPS3_EEEEEE+0x4e0>
   d2a7c:	stp	x19, x20, [sp, #16]
   d2a80:	mov	x19, x1
   d2a84:	add	x20, sp, #0x80
   d2a88:	ldr	x1, [x21, #4048]
   d2a8c:	stp	x25, x26, [sp, #64]
   d2a90:	mov	x26, x2
   d2a94:	ldr	x2, [x1]
   d2a98:	str	x2, [sp, #232]
   d2a9c:	mov	x2, #0x0                   	// #0
   d2aa0:	add	x22, x22, #0x8e8
   d2aa4:	mov	x1, x22
   d2aa8:	mov	x25, x0
   d2aac:	mov	x8, x20
   d2ab0:	mov	x0, x19
   d2ab4:	stp	x23, x24, [sp, #48]
   d2ab8:	mov	x24, x3
   d2abc:	mov	w23, #0x30                  	// #48
   d2ac0:	str	d8, [sp, #96]
   d2ac4:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2ac8:	ldr	w0, [x19]
   d2acc:	ldr	x2, [x19, #8]
   d2ad0:	ldr	x1, [sp, #128]
   d2ad4:	umaddl	x0, w0, w23, x2
   d2ad8:	cmp	x1, x0
   d2adc:	b.eq	d2da0 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x338>  // b.none
   d2ae0:	mov	x0, x19
   d2ae4:	mov	x8, x20
   d2ae8:	stp	x27, x28, [sp, #80]
   d2aec:	adrp	x27, 24d000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM15ExceptionHandleFvvEPS3_EEEEEE+0x4e0>
   d2af0:	add	x1, x27, #0xb18
   d2af4:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2af8:	ldr	w0, [x19]
   d2afc:	ldr	x2, [x19, #8]
   d2b00:	ldr	x1, [sp, #128]
   d2b04:	umaddl	x0, w0, w23, x2
   d2b08:	cmp	x1, x0
   d2b0c:	b.eq	d2d9c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2b10:	mov	x0, x19
   d2b14:	mov	x8, x20
   d2b18:	adrp	x28, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
   d2b1c:	add	x1, x28, #0xbe8
   d2b20:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2b24:	ldr	w0, [x19]
   d2b28:	ldr	x2, [x19, #8]
   d2b2c:	ldr	x1, [sp, #128]
   d2b30:	umaddl	x0, w0, w23, x2
   d2b34:	cmp	x1, x0
   d2b38:	b.eq	d2d9c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2b3c:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2b40:	mov	x8, x20
   d2b44:	add	x1, x0, #0xb50
   d2b48:	mov	x0, x19
   d2b4c:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2b50:	ldr	w0, [x19]
   d2b54:	ldr	x2, [x19, #8]
   d2b58:	ldr	x1, [sp, #128]
   d2b5c:	umaddl	x0, w0, w23, x2
   d2b60:	cmp	x1, x0
   d2b64:	b.eq	d2d9c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2b68:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2b6c:	mov	x8, x20
   d2b70:	add	x1, x0, #0xb58
   d2b74:	mov	x0, x19
   d2b78:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2b7c:	ldr	w0, [x19]
   d2b80:	ldr	x2, [x19, #8]
   d2b84:	ldr	x1, [sp, #128]
   d2b88:	umaddl	x0, w0, w23, x2
   d2b8c:	cmp	x1, x0
   d2b90:	b.eq	d2d9c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2b94:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2b98:	mov	x8, x20
   d2b9c:	add	x1, x0, #0xb60
   d2ba0:	mov	x0, x19
   d2ba4:	bl	f5478 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE10FindMemberEPKc>
   d2ba8:	ldr	w0, [x19]
   d2bac:	ldr	x2, [x19, #8]
   d2bb0:	ldr	x1, [sp, #128]
   d2bb4:	umaddl	x23, w0, w23, x2
   d2bb8:	cmp	x1, x23
   d2bbc:	b.eq	d2d9c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x334>  // b.none
   d2bc0:	mov	x0, x20
   d2bc4:	bl	aa2f0 <_ZN5drdds3msg5SteerC1Ev@plt>
   d2bc8:	mov	x1, x22
   d2bcc:	mov	x0, x19
   d2bd0:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2bd4:	bl	f5290 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE7IsFloatEv>
   d2bd8:	tst	w0, #0xff
   d2bdc:	b.eq	d2e10 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x3a8>  // b.none
   d2be0:	mov	x1, x22
   d2be4:	mov	x0, x19
   d2be8:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2bec:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2bf0:	fcvt	s8, d0
   d2bf4:	mov	x0, x20
   d2bf8:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2bfc:	bl	aa010 <_ZN5drdds3msg10SteerValue1xEv@plt>
   d2c00:	mov	x2, x0
   d2c04:	add	x1, x27, #0xb18
   d2c08:	mov	x0, x19
   d2c0c:	str	s8, [x2]
   d2c10:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2c14:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2c18:	fcvt	s8, d0
   d2c1c:	mov	x0, x20
   d2c20:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2c24:	bl	a8d40 <_ZN5drdds3msg10SteerValue1yEv@plt>
   d2c28:	mov	x2, x0
   d2c2c:	add	x1, x28, #0xbe8
   d2c30:	mov	x0, x19
   d2c34:	str	s8, [x2]
   d2c38:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2c3c:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2c40:	fcvt	s8, d0
   d2c44:	mov	x0, x20
   d2c48:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2c4c:	bl	a8150 <_ZN5drdds3msg10SteerValue1zEv@plt>
   d2c50:	mov	x2, x0
   d2c54:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2c58:	add	x1, x0, #0xb50
   d2c5c:	mov	x0, x19
   d2c60:	str	s8, [x2]
   d2c64:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2c68:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2c6c:	fcvt	s8, d0
   d2c70:	mov	x0, x20
   d2c74:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2c78:	bl	ab0c0 <_ZN5drdds3msg10SteerValue4rollEv@plt>
   d2c7c:	mov	x2, x0
   d2c80:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2c84:	add	x1, x0, #0xb58
   d2c88:	mov	x0, x19
   d2c8c:	str	s8, [x2]
   d2c90:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2c94:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2c98:	fcvt	s8, d0
   d2c9c:	mov	x0, x20
   d2ca0:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2ca4:	bl	a8650 <_ZN5drdds3msg10SteerValue5pitchEv@plt>
   d2ca8:	mov	x2, x0
   d2cac:	adrp	x0, 22e000 <ev_prepare_start+0x8c>
   d2cb0:	add	x1, x0, #0xb60
   d2cb4:	mov	x0, x19
   d2cb8:	str	s8, [x2]
   d2cbc:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2cc0:	bl	f4928 <_ZNK9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEE9GetDoubleEv>
   d2cc4:	fcvt	s8, d0
   d2cc8:	mov	x0, x20
   d2ccc:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
   d2cd0:	bl	aab30 <_ZN5drdds3msg10SteerValue3yawEv@plt>
   d2cd4:	str	s8, [x0]
   d2cd8:	adrp	x19, 2d3000 <__data_start>
   d2cdc:	add	x22, x19, #0x478
   d2ce0:	add	x0, x22, #0x7f8
   d2ce4:	ldarb	w1, [x0]
   d2ce8:	tbnz	w1, #0, d2cf4 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x28c>
   d2cec:	bl	a99b0 <__cxa_guard_acquire@plt>
   d2cf0:	cbnz	w0, d2ec4 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x45c>
   d2cf4:	bl	aa6e0 <_ZNSt6chrono3_V212system_clock3nowEv@plt>
   d2cf8:	mov	x1, #0x94b3                	// #38067
   d2cfc:	add	x3, x19, #0x478
   d2d00:	movk	x1, #0x26d6, lsl #16
   d2d04:	movk	x1, #0xbe8, lsl #32
   d2d08:	movk	x1, #0x112e, lsl #48
   d2d0c:	ldr	x4, [x24, #8]
   d2d10:	smulh	x1, x0, x1
   d2d14:	ldr	x2, [x3, #2056]
   d2d18:	asr	x1, x1, #26
   d2d1c:	sub	x22, x1, x0, asr #63
   d2d20:	cmp	x2, x4
   d2d24:	b.eq	d2ef8 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x490>  // b.none
   d2d28:	add	x28, x19, #0x478
   d2d2c:	adrp	x23, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d2d30:	add	x27, x28, #0x800
   d2d34:	add	x1, x23, #0xd78
   d2d38:	mov	x0, x27
   d2d3c:	bl	aaf10 <_ZNKSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEE7compareEPKc@plt>
   d2d40:	cbnz	w0, d2ea4 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x43c>
   d2d44:	add	x19, x19, #0x478
   d2d48:	mov	x1, x20
   d2d4c:	ldr	x0, [x25, #344]
   d2d50:	str	x22, [x19, #2080]
   d2d54:	add	x0, x0, #0x110
   d2d58:	bl	225468 <_ZN10VelControl11sendRealVelERN5drdds3msg5SteerE>
   d2d5c:	mov	x0, x20
   d2d60:	bl	a8a00 <_ZN5drdds3msg5SteerD1Ev@plt>
   d2d64:	ldp	x27, x28, [sp, #80]
   d2d68:	ldr	x21, [x21, #4048]
   d2d6c:	ldr	x0, [sp, #232]
   d2d70:	ldr	x1, [x21]
   d2d74:	subs	x0, x0, x1
   d2d78:	mov	x1, #0x0                   	// #0
   d2d7c:	b.ne	d300c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5a4>  // b.any
   d2d80:	ldp	x19, x20, [sp, #16]
   d2d84:	ldp	x21, x22, [sp, #32]
   d2d88:	ldp	x23, x24, [sp, #48]
   d2d8c:	ldp	x25, x26, [sp, #64]
   d2d90:	ldr	d8, [sp, #96]
   d2d94:	ldp	x29, x30, [sp], #240
   d2d98:	ret
   d2d9c:	ldp	x27, x28, [sp, #80]
   d2da0:	mov	w2, #0xe004                	// #57348
   d2da4:	add	x19, sp, #0xa8
   d2da8:	add	x22, sp, #0xc8
   d2dac:	mov	x0, x19
   d2db0:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d2db4:	add	x1, x1, #0xd78
   d2db8:	str	w2, [sp, #128]
   d2dbc:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d2dc0:	mov	x2, x20
   d2dc4:	mov	x1, x24
   d2dc8:	mov	x0, x25
   d2dcc:	mov	x3, x19
   d2dd0:	mov	x8, x22
   d2dd4:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d2dd8:	mov	x1, x22
   d2ddc:	mov	x0, x26
   d2de0:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d2de4:	add	x22, x22, #0x10
   d2de8:	ldr	x0, [sp, #200]
   d2dec:	cmp	x0, x22
   d2df0:	b.eq	d2df8 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x390>  // b.none
   d2df4:	bl	a7460 <_ZdlPv@plt>
   d2df8:	ldr	x0, [sp, #168]
   d2dfc:	add	x19, x19, #0x10
   d2e00:	cmp	x0, x19
   d2e04:	b.eq	d2d68 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x300>  // b.none
   d2e08:	bl	a7460 <_ZdlPv@plt>
   d2e0c:	b	d2d68 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x300>
   d2e10:	mov	x1, x22
   d2e14:	mov	x0, x19
   d2e18:	bl	f4838 <_ZN9rapidjson12GenericValueINS_4UTF8IcEENS_19MemoryPoolAllocatorINS_12CrtAllocatorEEEEixIKcEENS_8internal9DisableIfINS9_15RemoveSfinaeTagIPFRNS9_9SfinaeTagENS9_7NotExprINS9_6IsSameINS9_11RemoveConstIT_E4TypeEcEEEEEE4TypeERS6_E4TypeEPSH_>
   d2e1c:	ldrh	w0, [x0, #22]
   d2e20:	tbz	w0, #10, d2cd8 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x270>
   d2e24:	ldr	x0, [x25, #240]
   d2e28:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d2e2c:	add	x1, x1, #0xe70
   d2e30:	bl	f4e00 <_ZN8DrLogger4warnIJEEEvPKcDpOT_>
   d2e34:	mov	w2, #0xe005                	// #57349
   d2e38:	add	x22, sp, #0xc8
   d2e3c:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d2e40:	mov	x0, x22
   d2e44:	add	x1, x1, #0xd78
   d2e48:	str	w2, [sp, #120]
   d2e4c:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d2e50:	add	x19, sp, #0xa8
   d2e54:	mov	x1, x24
   d2e58:	mov	x0, x25
   d2e5c:	mov	x8, x19
   d2e60:	mov	x3, x22
   d2e64:	add	x2, sp, #0x78
   d2e68:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d2e6c:	mov	x1, x19
   d2e70:	mov	x0, x26
   d2e74:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d2e78:	add	x19, x19, #0x10
   d2e7c:	ldr	x0, [sp, #168]
   d2e80:	cmp	x0, x19
   d2e84:	b.eq	d2e8c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x424>  // b.none
   d2e88:	bl	a7460 <_ZdlPv@plt>
   d2e8c:	ldr	x0, [sp, #200]
   d2e90:	add	x22, x22, #0x10
   d2e94:	cmp	x0, x22
   d2e98:	b.eq	d2d5c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>  // b.none
   d2e9c:	bl	a7460 <_ZdlPv@plt>
   d2ea0:	b	d2d5c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>
   d2ea4:	ldr	x0, [x28, #2080]
   d2ea8:	sub	x0, x22, x0
   d2eac:	cmp	x0, #0x2
   d2eb0:	b.le	d2f10 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x4a8>
   d2eb4:	mov	x1, x24
   d2eb8:	mov	x0, x27
   d2ebc:	bl	a8ea0 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEE9_M_assignERKS4_@plt>
   d2ec0:	b	d2d44 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2dc>
   d2ec4:	adrp	x1, 23f000 <_ZTSNSt6thread11_State_implINS_8_InvokerISt5tupleIJM9heratBeatFvvEPS3_EEEEEE+0x2fd0>
   d2ec8:	add	x0, x22, #0x800
   d2ecc:	add	x1, x1, #0xd78
   d2ed0:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d2ed4:	adrp	x0, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d2ed8:	add	x1, x22, #0x800
   d2edc:	adrp	x2, 2d3000 <__data_start>
   d2ee0:	add	x2, x2, #0x8
   d2ee4:	ldr	x0, [x0, #3992]
   d2ee8:	bl	aa9d0 <__cxa_atexit@plt>
   d2eec:	add	x0, x22, #0x7f8
   d2ef0:	bl	aa0a0 <__cxa_guard_release@plt>
   d2ef4:	b	d2cf4 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x28c>
   d2ef8:	cbz	x2, d2d44 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2dc>
   d2efc:	ldr	x1, [x24]
   d2f00:	ldr	x0, [x3, #2048]
   d2f04:	bl	a8bf0 <memcmp@plt>
   d2f08:	cbz	w0, d2d44 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2dc>
   d2f0c:	b	d2d28 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2c0>
   d2f10:	ldr	x5, [x24]
   d2f14:	add	x27, sp, #0x78
   d2f18:	ldr	x0, [x25, #240]
   d2f1c:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d2f20:	ldr	x4, [x28, #2048]
   d2f24:	mov	x3, x27
   d2f28:	add	x2, sp, #0x70
   d2f2c:	add	x1, x1, #0xe08
   d2f30:	stp	x5, x4, [sp, #112]
   d2f34:	bl	f52c8 <_ZN8DrLogger4infoIJPKcS2_EEEvS2_DpOT_>
   d2f38:	adrp	x22, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   d2f3c:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d2f40:	mov	x2, #0x4                   	// #4
   d2f44:	add	x1, x1, #0xe38
   d2f48:	ldr	x0, [x22, #3680]
   d2f4c:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2f50:	ldp	x1, x2, [x24]
   d2f54:	ldr	x0, [x22, #3680]
   d2f58:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2f5c:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d2f60:	mov	x22, x0
   d2f64:	add	x1, x1, #0xe40
   d2f68:	mov	x2, #0x19                  	// #25
   d2f6c:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2f70:	add	x19, x19, #0x478
   d2f74:	mov	x0, x22
   d2f78:	ldr	x1, [x19, #2048]
   d2f7c:	ldr	x2, [x19, #2056]
   d2f80:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2f84:	adrp	x1, 231000 <_IO_stdin_used+0x2530>
   d2f88:	mov	x19, x0
   d2f8c:	add	x1, x1, #0xe60
   d2f90:	mov	x2, #0xa                   	// #10
   d2f94:	bl	a88c0 <_ZSt16__ostream_insertIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_PKS3_l@plt>
   d2f98:	mov	x0, x19
   d2f9c:	bl	a8a10 <_ZSt4endlIcSt11char_traitsIcEERSt13basic_ostreamIT_T0_ES6_@plt>
   d2fa0:	mov	w2, #0xe006                	// #57350
   d2fa4:	add	x19, sp, #0xa8
   d2fa8:	add	x1, x23, #0xd78
   d2fac:	mov	x0, x19
   d2fb0:	str	w2, [sp, #120]
   d2fb4:	bl	c3a78 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEC2IS3_EEPKcRKS3_.constprop.0>
   d2fb8:	add	x22, sp, #0xc8
   d2fbc:	mov	x2, x27
   d2fc0:	mov	x1, x24
   d2fc4:	mov	x0, x25
   d2fc8:	mov	x8, x22
   d2fcc:	mov	x3, x19
   d2fd0:	bl	d1c08 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE>
   d2fd4:	mov	x1, x22
   d2fd8:	mov	x0, x26
   d2fdc:	bl	a9f90 <_ZNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEaSEOS4_@plt>
   d2fe0:	add	x22, x22, #0x10
   d2fe4:	ldr	x0, [sp, #200]
   d2fe8:	cmp	x0, x22
   d2fec:	b.eq	d2ff4 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x58c>  // b.none
   d2ff0:	bl	a7460 <_ZdlPv@plt>
   d2ff4:	ldr	x0, [sp, #168]
   d2ff8:	add	x19, x19, #0x10
   d2ffc:	cmp	x0, x19
   d3000:	b.eq	d2d5c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>  // b.none
   d3004:	bl	a7460 <_ZdlPv@plt>
   d3008:	b	d2d5c <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x2f4>
   d300c:	stp	x27, x28, [sp, #80]
   d3010:	bl	ab600 <__stack_chk_fail@plt>
   d3014:	mov	x1, x0
   d3018:	add	x19, x19, #0x478
   d301c:	add	x0, x19, #0x7f8
   d3020:	mov	x19, x1
   d3024:	bl	a70e0 <__cxa_guard_abort@plt>
   d3028:	mov	x0, x20
   d302c:	bl	a8a00 <_ZN5drdds3msg5SteerD1Ev@plt>
   d3030:	mov	x0, x19
   d3034:	bl	a7a60 <_Unwind_Resume@plt>
   d3038:	ldr	x1, [sp, #168]
   d303c:	add	x19, x19, #0x10
   d3040:	mov	x21, x0
   d3044:	cmp	x1, x19
   d3048:	b.eq	d3054 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5ec>  // b.none
   d304c:	mov	x0, x1
   d3050:	bl	a7460 <_ZdlPv@plt>
   d3054:	mov	x19, x21
   d3058:	b	d3028 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5c0>
   d305c:	ldr	x1, [sp, #200]
   d3060:	add	x22, x22, #0x10
   d3064:	mov	x19, x0
   d3068:	cmp	x1, x22
   d306c:	b.eq	d3028 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5c0>  // b.none
   d3070:	mov	x0, x1
   d3074:	bl	a7460 <_ZdlPv@plt>
   d3078:	b	d3028 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5c0>
   d307c:	mov	x19, x0
   d3080:	b	d3028 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5c0>
   d3084:	ldr	x1, [sp, #168]
   d3088:	stp	x27, x28, [sp, #80]
   d308c:	add	x19, x19, #0x10
   d3090:	mov	x20, x0
   d3094:	cmp	x1, x19
   d3098:	b.eq	d30a4 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x63c>  // b.none
   d309c:	mov	x0, x1
   d30a0:	bl	a7460 <_ZdlPv@plt>
   d30a4:	mov	x0, x20
   d30a8:	bl	a7a60 <_Unwind_Resume@plt>
   d30ac:	nop
