
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000001b54f0 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE>:
  1b54f0:	stp	x29, x30, [sp, #-144]!
  1b54f4:	mov	x29, sp
  1b54f8:	stp	x19, x20, [sp, #16]
  1b54fc:	adrp	x19, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
  1b5500:	mov	x20, x0
  1b5504:	ldr	x0, [x19, #4048]
  1b5508:	stp	x21, x22, [sp, #32]
  1b550c:	mov	x21, x1
  1b5510:	ldr	x22, [x20, #2672]
  1b5514:	ldr	x1, [x0]
  1b5518:	str	x1, [sp, #136]
  1b551c:	mov	x1, #0x0                   	// #0
  1b5520:	cbz	x22, 1b5558 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0x68>
  1b5524:	mov	x1, x21
  1b5528:	mov	x0, x22
  1b552c:	bl	a7ee0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEE5WriteEPKNS1_5SteerE@plt>
  1b5530:	ldr	x19, [x19, #4048]
  1b5534:	ldr	x1, [sp, #136]
  1b5538:	ldr	x2, [x19]
  1b553c:	subs	x1, x1, x2
  1b5540:	mov	x2, #0x0                   	// #0
  1b5544:	b.ne	1b5618 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0x128>  // b.any
  1b5548:	ldp	x19, x20, [sp, #16]
  1b554c:	ldp	x21, x22, [sp, #32]
  1b5550:	ldp	x29, x30, [sp], #144
  1b5554:	ret
  1b5558:	adrp	x0, 242000 <_ZL11kSocketPath+0x60>
  1b555c:	add	x0, x0, #0xee0
  1b5560:	stp	x23, x24, [sp, #48]
  1b5564:	add	x23, sp, #0x68
  1b5568:	add	x24, sp, #0x48
  1b556c:	ldrh	w2, [x0, #4]
  1b5570:	add	x1, x23, #0x10
  1b5574:	ldr	w3, [x0]
  1b5578:	add	x7, x24, #0x10
  1b557c:	str	w3, [sp, #120]
  1b5580:	mov	x4, #0x6                   	// #6
  1b5584:	strb	wzr, [sp, #126]
  1b5588:	mov	w5, #0x7472                	// #29810
  1b558c:	mov	x6, #0x2                   	// #2
  1b5590:	strh	w2, [x23, #20]
  1b5594:	mov	x0, #0x18                  	// #24
  1b5598:	stp	x7, x6, [sp, #72]
  1b559c:	strh	w5, [sp, #88]
  1b55a0:	strb	wzr, [sp, #90]
  1b55a4:	stp	x1, x4, [sp, #104]
  1b55a8:	bl	a9290 <_Znwm@plt>
  1b55ac:	mov	x4, x24
  1b55b0:	mov	x22, x0
  1b55b4:	mov	x1, x23
  1b55b8:	mov	w3, #0x0                   	// #0
  1b55bc:	mov	w2, #0x0                   	// #0
  1b55c0:	bl	aacb0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEEC1ENSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEEibS9_@plt>
  1b55c4:	ldr	x0, [sp, #72]
  1b55c8:	add	x24, x24, #0x10
  1b55cc:	cmp	x0, x24
  1b55d0:	b.eq	1b55d8 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0xe8>  // b.none
  1b55d4:	bl	a7460 <_ZdlPv@plt>
  1b55d8:	ldr	x0, [sp, #104]
  1b55dc:	add	x23, x23, #0x10
  1b55e0:	cmp	x0, x23
  1b55e4:	b.eq	1b55ec <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0xfc>  // b.none
  1b55e8:	bl	a7460 <_ZdlPv@plt>
  1b55ec:	ldr	x23, [x20, #2672]
  1b55f0:	str	x22, [x20, #2672]
  1b55f4:	cbz	x23, 1b5610 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0x120>
  1b55f8:	mov	x0, x23
  1b55fc:	bl	a68e0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEED1Ev@plt>
  1b5600:	mov	x0, x23
  1b5604:	mov	x1, #0x18                  	// #24
  1b5608:	bl	a67e0 <_ZdlPvm@plt>
  1b560c:	ldr	x22, [x20, #2672]
  1b5610:	ldp	x23, x24, [sp, #48]
  1b5614:	b	1b5524 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0x34>
  1b5618:	stp	x23, x24, [sp, #48]
  1b561c:	bl	ab600 <__stack_chk_fail@plt>
  1b5620:	mov	x19, x0
  1b5624:	mov	x1, #0x18                  	// #24
  1b5628:	mov	x0, x22
  1b562c:	bl	a67e0 <_ZdlPvm@plt>
  1b5630:	ldr	x0, [sp, #72]
  1b5634:	add	x24, x24, #0x10
  1b5638:	cmp	x0, x24
  1b563c:	b.eq	1b5644 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0x154>  // b.none
  1b5640:	bl	a7460 <_ZdlPv@plt>
  1b5644:	ldr	x0, [sp, #104]
  1b5648:	add	x23, x23, #0x10
  1b564c:	cmp	x0, x23
  1b5650:	b.eq	1b5658 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0x168>  // b.none
  1b5654:	bl	a7460 <_ZdlPv@plt>
  1b5658:	mov	x0, x19
  1b565c:	bl	a7a60 <_Unwind_Resume@plt>
  1b5660:	mov	x19, x0
  1b5664:	b	1b5630 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE+0x140>

00000000001b5668 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE>:
  1b5668:	stp	x29, x30, [sp, #-144]!
  1b566c:	mov	x29, sp
  1b5670:	stp	x19, x20, [sp, #16]
  1b5674:	adrp	x19, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
  1b5678:	mov	x20, x0
  1b567c:	ldr	x0, [x19, #4048]
  1b5680:	stp	x21, x22, [sp, #32]
  1b5684:	mov	x21, x1
  1b5688:	ldr	x22, [x20, #2680]
  1b568c:	ldr	x1, [x0]
  1b5690:	str	x1, [sp, #136]
  1b5694:	mov	x1, #0x0                   	// #0
  1b5698:	cbz	x22, 1b56d0 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0x68>
  1b569c:	mov	x1, x21
  1b56a0:	mov	x0, x22
  1b56a4:	bl	a7ee0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEE5WriteEPKNS1_5SteerE@plt>
  1b56a8:	ldr	x19, [x19, #4048]
  1b56ac:	ldr	x1, [sp, #136]
  1b56b0:	ldr	x2, [x19]
  1b56b4:	subs	x1, x1, x2
  1b56b8:	mov	x2, #0x0                   	// #0
  1b56bc:	b.ne	1b5790 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0x128>  // b.any
  1b56c0:	ldp	x19, x20, [sp, #16]
  1b56c4:	ldp	x21, x22, [sp, #32]
  1b56c8:	ldp	x29, x30, [sp], #144
  1b56cc:	ret
  1b56d0:	adrp	x0, 242000 <_ZL11kSocketPath+0x60>
  1b56d4:	add	x0, x0, #0xee8
  1b56d8:	stp	x23, x24, [sp, #48]
  1b56dc:	add	x23, sp, #0x68
  1b56e0:	add	x24, sp, #0x48
  1b56e4:	ldr	x2, [x0]
  1b56e8:	str	x2, [sp, #120]
  1b56ec:	ldur	w2, [x0, #7]
  1b56f0:	add	x1, x23, #0x10
  1b56f4:	add	x6, x24, #0x10
  1b56f8:	strb	wzr, [sp, #131]
  1b56fc:	mov	x3, #0xb                   	// #11
  1b5700:	mov	w4, #0x7472                	// #29810
  1b5704:	mov	x5, #0x2                   	// #2
  1b5708:	stur	w2, [x23, #23]
  1b570c:	mov	x0, #0x18                  	// #24
  1b5710:	stp	x6, x5, [sp, #72]
  1b5714:	strh	w4, [sp, #88]
  1b5718:	strb	wzr, [sp, #90]
  1b571c:	stp	x1, x3, [sp, #104]
  1b5720:	bl	a9290 <_Znwm@plt>
  1b5724:	mov	x4, x24
  1b5728:	mov	x22, x0
  1b572c:	mov	x1, x23
  1b5730:	mov	w3, #0x0                   	// #0
  1b5734:	mov	w2, #0x0                   	// #0
  1b5738:	bl	aacb0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEEC1ENSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEEibS9_@plt>
  1b573c:	ldr	x0, [sp, #72]
  1b5740:	add	x24, x24, #0x10
  1b5744:	cmp	x0, x24
  1b5748:	b.eq	1b5750 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0xe8>  // b.none
  1b574c:	bl	a7460 <_ZdlPv@plt>
  1b5750:	ldr	x0, [sp, #104]
  1b5754:	add	x23, x23, #0x10
  1b5758:	cmp	x0, x23
  1b575c:	b.eq	1b5764 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0xfc>  // b.none
  1b5760:	bl	a7460 <_ZdlPv@plt>
  1b5764:	ldr	x23, [x20, #2680]
  1b5768:	str	x22, [x20, #2680]
  1b576c:	cbz	x23, 1b5788 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0x120>
  1b5770:	mov	x0, x23
  1b5774:	bl	a68e0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEED1Ev@plt>
  1b5778:	mov	x0, x23
  1b577c:	mov	x1, #0x18                  	// #24
  1b5780:	bl	a67e0 <_ZdlPvm@plt>
  1b5784:	ldr	x22, [x20, #2680]
  1b5788:	ldp	x23, x24, [sp, #48]
  1b578c:	b	1b569c <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0x34>
  1b5790:	stp	x23, x24, [sp, #48]
  1b5794:	bl	ab600 <__stack_chk_fail@plt>
  1b5798:	mov	x19, x0
  1b579c:	mov	x1, #0x18                  	// #24
  1b57a0:	mov	x0, x22
  1b57a4:	bl	a67e0 <_ZdlPvm@plt>
  1b57a8:	ldr	x0, [sp, #72]
  1b57ac:	add	x24, x24, #0x10
  1b57b0:	cmp	x0, x24
  1b57b4:	b.eq	1b57bc <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0x154>  // b.none
  1b57b8:	bl	a7460 <_ZdlPv@plt>
  1b57bc:	ldr	x0, [sp, #104]
  1b57c0:	add	x23, x23, #0x10
  1b57c4:	cmp	x0, x23
  1b57c8:	b.eq	1b57d0 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0x168>  // b.none
  1b57cc:	bl	a7460 <_ZdlPv@plt>
  1b57d0:	mov	x0, x19
  1b57d4:	bl	a7a60 <_Unwind_Resume@plt>
  1b57d8:	mov	x19, x0
  1b57dc:	b	1b57a8 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE+0x140>

00000000001b57e0 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE>:
  1b57e0:	stp	x29, x30, [sp, #-144]!
  1b57e4:	mov	x29, sp
  1b57e8:	stp	x19, x20, [sp, #16]
  1b57ec:	adrp	x19, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
  1b57f0:	mov	x20, x0
  1b57f4:	ldr	x0, [x19, #4048]
  1b57f8:	stp	x21, x22, [sp, #32]
  1b57fc:	mov	x21, x1
  1b5800:	ldr	x22, [x20, #2688]
  1b5804:	ldr	x1, [x0]
  1b5808:	str	x1, [sp, #136]
  1b580c:	mov	x1, #0x0                   	// #0
  1b5810:	cbz	x22, 1b5848 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0x68>
  1b5814:	mov	x1, x21
  1b5818:	mov	x0, x22
  1b581c:	bl	a7ee0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEE5WriteEPKNS1_5SteerE@plt>
  1b5820:	ldr	x19, [x19, #4048]
  1b5824:	ldr	x1, [sp, #136]
  1b5828:	ldr	x2, [x19]
  1b582c:	subs	x1, x1, x2
  1b5830:	mov	x2, #0x0                   	// #0
  1b5834:	b.ne	1b5908 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0x128>  // b.any
  1b5838:	ldp	x19, x20, [sp, #16]
  1b583c:	ldp	x21, x22, [sp, #32]
  1b5840:	ldp	x29, x30, [sp], #144
  1b5844:	ret
  1b5848:	adrp	x0, 242000 <_ZL11kSocketPath+0x60>
  1b584c:	add	x0, x0, #0xef8
  1b5850:	stp	x23, x24, [sp, #48]
  1b5854:	add	x23, sp, #0x68
  1b5858:	add	x24, sp, #0x48
  1b585c:	ldr	x2, [x0]
  1b5860:	str	x2, [sp, #120]
  1b5864:	ldur	x2, [x0, #5]
  1b5868:	add	x1, x23, #0x10
  1b586c:	add	x6, x24, #0x10
  1b5870:	strb	wzr, [sp, #133]
  1b5874:	mov	x3, #0xd                   	// #13
  1b5878:	mov	w4, #0x7472                	// #29810
  1b587c:	mov	x5, #0x2                   	// #2
  1b5880:	stur	x2, [x23, #21]
  1b5884:	mov	x0, #0x18                  	// #24
  1b5888:	stp	x6, x5, [sp, #72]
  1b588c:	strh	w4, [sp, #88]
  1b5890:	strb	wzr, [sp, #90]
  1b5894:	stp	x1, x3, [sp, #104]
  1b5898:	bl	a9290 <_Znwm@plt>
  1b589c:	mov	x4, x24
  1b58a0:	mov	x22, x0
  1b58a4:	mov	x1, x23
  1b58a8:	mov	w3, #0x0                   	// #0
  1b58ac:	mov	w2, #0x0                   	// #0
  1b58b0:	bl	aacb0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEEC1ENSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEEibS9_@plt>
  1b58b4:	ldr	x0, [sp, #72]
  1b58b8:	add	x24, x24, #0x10
  1b58bc:	cmp	x0, x24
  1b58c0:	b.eq	1b58c8 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0xe8>  // b.none
  1b58c4:	bl	a7460 <_ZdlPv@plt>
  1b58c8:	ldr	x0, [sp, #104]
  1b58cc:	add	x23, x23, #0x10
  1b58d0:	cmp	x0, x23
  1b58d4:	b.eq	1b58dc <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0xfc>  // b.none
  1b58d8:	bl	a7460 <_ZdlPv@plt>
  1b58dc:	ldr	x23, [x20, #2688]
  1b58e0:	str	x22, [x20, #2688]
  1b58e4:	cbz	x23, 1b5900 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0x120>
  1b58e8:	mov	x0, x23
  1b58ec:	bl	a68e0 <_ZN12DrDDSChannelIN5drdds3msg15SteerPubSubTypeEED1Ev@plt>
  1b58f0:	mov	x0, x23
  1b58f4:	mov	x1, #0x18                  	// #24
  1b58f8:	bl	a67e0 <_ZdlPvm@plt>
  1b58fc:	ldr	x22, [x20, #2688]
  1b5900:	ldp	x23, x24, [sp, #48]
  1b5904:	b	1b5814 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0x34>
  1b5908:	stp	x23, x24, [sp, #48]
  1b590c:	bl	ab600 <__stack_chk_fail@plt>
  1b5910:	mov	x19, x0
  1b5914:	mov	x1, #0x18                  	// #24
  1b5918:	mov	x0, x22
  1b591c:	bl	a67e0 <_ZdlPvm@plt>
  1b5920:	ldr	x0, [sp, #72]
  1b5924:	add	x24, x24, #0x10
  1b5928:	cmp	x0, x24
  1b592c:	b.eq	1b5934 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0x154>  // b.none
  1b5930:	bl	a7460 <_ZdlPv@plt>
  1b5934:	ldr	x0, [sp, #104]
  1b5938:	add	x23, x23, #0x10
  1b593c:	cmp	x0, x23
  1b5940:	b.eq	1b5948 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0x168>  // b.none
  1b5944:	bl	a7460 <_ZdlPv@plt>
  1b5948:	mov	x0, x19
  1b594c:	bl	a7a60 <_Unwind_Resume@plt>
  1b5950:	mov	x19, x0
  1b5954:	b	1b5920 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE+0x140>

00000000001b5958 <_ZN9DDSWorker10IsChargingEv>:
  1b5958:	stp	x29, x30, [sp, #-16]!
  1b595c:	add	x0, x0, #0x6a0
  1b5960:	mov	x29, sp
  1b5964:	bl	a7820 <_ZN5drdds3msg9StdStatus5stateEv@plt>
  1b5968:	ldr	w0, [x0]
  1b596c:	ldp	x29, x30, [sp], #16
  1b5970:	cmp	w0, #0x2
  1b5974:	cset	w0, eq  // eq = none
  1b5978:	ret
  1b597c:	nop

00000000001b5980 <_ZN9DDSWorker6IsIdleEv>:
  1b5980:	stp	x29, x30, [sp, #-16]!
  1b5984:	add	x0, x0, #0x6a0
  1b5988:	mov	x29, sp
  1b598c:	bl	a7820 <_ZN5drdds3msg9StdStatus5stateEv@plt>
  1b5990:	ldr	w0, [x0]
  1b5994:	ldp	x29, x30, [sp], #16
  1b5998:	cmp	w0, #0x0
  1b599c:	cset	w0, eq  // eq = none
  1b59a0:	ret
  1b59a4:	nop

00000000001b59a8 <_ZN9DDSWorker8SendGoalEffffNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEEj>:
  1b59a8:	sub	sp, sp, #0x570
  1b59ac:	stp	x29, x30, [sp]
  1b59b0:	mov	x29, sp
  1b59b4:	stp	x23, x24, [sp, #48]
  1b59b8:	adrp	x23, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
  1b59bc:	ldr	x3, [x23, #4048]
  1b59c0:	stp	x21, x22, [sp, #32]
  1b59c4:	mov	x21, x1
  1b59c8:	ldr	x1, [x3]
  1b59cc:	str	x1, [sp, #1384]
  1b59d0:	mov	x1, #0x0                   	// #0
  1b59d4:	stp	x19, x20, [sp, #16]
  1b59d8:	add	x19, sp, #0x108
  1b59dc:	mov	x22, x0
  1b59e0:	mov	x0, x19
  1b59e4:	stp	x25, x26, [sp, #64]
  1b59e8:	add	x25, sp, #0x78
  1b59ec:	str	w2, [sp, #92]
  1b59f0:	stp	s3, s2, [sp, #96]
  1b59f4:	stp	s1, s0, [sp, #104]
  1b59f8:	bl	a6980 <_ZN5drdds3srv26PoseStampedToInt32_RequestC1Ev@plt>
  1b59fc:	mov	x0, x25
