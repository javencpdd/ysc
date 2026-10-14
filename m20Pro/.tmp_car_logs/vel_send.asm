
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

0000000000225210 <_ZN10VelControl7sendVelERN5drdds3msg5SteerE>:
  225210:	stp	x29, x30, [sp, #-64]!
  225214:	mov	x29, sp
  225218:	stp	x19, x20, [sp, #16]
  22521c:	mov	x19, x1
  225220:	mov	x20, x0
  225224:	stp	x21, x22, [sp, #32]
  225228:	mov	x22, #0xf7cf                	// #63439
  22522c:	movk	x22, #0xe353, lsl #16
  225230:	str	d8, [sp, #48]
  225234:	bl	aa6e0 <_ZNSt6chrono3_V212system_clock3nowEv@plt>
  225238:	mov	x2, #0x94b3                	// #38067
  22523c:	mov	x1, x0
  225240:	movk	x2, #0x26d6, lsl #16
  225244:	movk	x22, #0x9ba5, lsl #32
  225248:	movk	x2, #0xbe8, lsl #32
  22524c:	movk	x22, #0x20c4, lsl #48
  225250:	movk	x2, #0x112e, lsl #48
  225254:	mov	x0, x19
  225258:	smulh	x22, x1, x22
  22525c:	smulh	x2, x1, x2
  225260:	asr	x22, x22, #7
  225264:	asr	x2, x2, #26
  225268:	sub	x21, x2, x1, asr #63
  22526c:	sub	w22, w22, w2
  225270:	bl	ab4c0 <_ZN5drdds3msg5Steer6headerEv@plt>
  225274:	bl	a76e0 <_ZN5drdds3msg8MetaType9timestampEv@plt>
  225278:	bl	a8980 <_ZN5drdds3msg9Timestamp4nsecEv@plt>
  22527c:	mov	x1, x0
  225280:	mov	x0, x19
  225284:	str	w22, [x1]
  225288:	bl	ab4c0 <_ZN5drdds3msg5Steer6headerEv@plt>
  22528c:	bl	a76e0 <_ZN5drdds3msg8MetaType9timestampEv@plt>
  225290:	bl	a71b0 <_ZN5drdds3msg9Timestamp3secEv@plt>
  225294:	mov	x1, x0
  225298:	mov	x0, x19
  22529c:	str	w21, [x1]
  2252a0:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  2252a4:	bl	aa010 <_ZN5drdds3msg10SteerValue1xEv@plt>
  2252a8:	ldr	s0, [x0]
  2252ac:	ldp	s1, s2, [x20, #188]
  2252b0:	bl	2281a8 <_ZN5utils13limitAbsValueEfff>
  2252b4:	fmov	s8, s0
  2252b8:	mov	x0, x19
  2252bc:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  2252c0:	bl	aa010 <_ZN5drdds3msg10SteerValue1xEv@plt>
  2252c4:	mov	x1, x0
  2252c8:	mov	x0, x19
  2252cc:	str	s8, [x1]
  2252d0:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  2252d4:	bl	a8d40 <_ZN5drdds3msg10SteerValue1yEv@plt>
  2252d8:	ldr	s0, [x0]
  2252dc:	ldp	s1, s2, [x20, #188]
  2252e0:	bl	2281a8 <_ZN5utils13limitAbsValueEfff>
  2252e4:	fmov	s8, s0
  2252e8:	mov	x0, x19
  2252ec:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  2252f0:	bl	a8d40 <_ZN5drdds3msg10SteerValue1yEv@plt>
  2252f4:	mov	x1, x0
  2252f8:	mov	x0, x19
  2252fc:	str	s8, [x1]
  225300:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225304:	bl	a8150 <_ZN5drdds3msg10SteerValue1zEv@plt>
  225308:	ldr	s0, [x0]
  22530c:	ldp	s1, s2, [x20, #188]
  225310:	bl	2281a8 <_ZN5utils13limitAbsValueEfff>
  225314:	fmov	s8, s0
  225318:	mov	x0, x19
  22531c:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225320:	bl	a8150 <_ZN5drdds3msg10SteerValue1zEv@plt>
  225324:	mov	x1, x0
  225328:	mov	x0, x19
  22532c:	str	s8, [x1]
  225330:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225334:	bl	aab30 <_ZN5drdds3msg10SteerValue3yawEv@plt>
  225338:	ldr	s0, [x0]
  22533c:	ldp	s1, s2, [x20, #188]
  225340:	bl	2281a8 <_ZN5utils13limitAbsValueEfff>
  225344:	fmov	s8, s0
  225348:	mov	x0, x19
  22534c:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225350:	bl	aab30 <_ZN5drdds3msg10SteerValue3yawEv@plt>
  225354:	mov	x1, x0
  225358:	mov	x0, x19
  22535c:	str	s8, [x1]
  225360:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225364:	bl	ab0c0 <_ZN5drdds3msg10SteerValue4rollEv@plt>
  225368:	ldr	s0, [x0]
  22536c:	ldp	s1, s2, [x20, #188]
  225370:	bl	2281a8 <_ZN5utils13limitAbsValueEfff>
  225374:	fmov	s8, s0
  225378:	mov	x0, x19
  22537c:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225380:	bl	ab0c0 <_ZN5drdds3msg10SteerValue4rollEv@plt>
  225384:	mov	x1, x0
  225388:	mov	x0, x19
  22538c:	str	s8, [x1]
  225390:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225394:	bl	a8650 <_ZN5drdds3msg10SteerValue5pitchEv@plt>
  225398:	ldr	s0, [x0]
  22539c:	ldp	s1, s2, [x20, #188]
  2253a0:	bl	2281a8 <_ZN5utils13limitAbsValueEfff>
  2253a4:	fmov	s8, s0
  2253a8:	mov	x0, x19
  2253ac:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  2253b0:	bl	a8650 <_ZN5drdds3msg10SteerValue5pitchEv@plt>
  2253b4:	ldr	w1, [x20, #132]
  2253b8:	str	s8, [x0]
  2253bc:	cmp	w1, #0x1
  2253c0:	b.eq	225410 <_ZN10VelControl7sendVelERN5drdds3msg5SteerE+0x200>  // b.none
  2253c4:	ldr	w0, [x20, #184]
  2253c8:	cbz	w0, 2253e8 <_ZN10VelControl7sendVelERN5drdds3msg5SteerE+0x1d8>
  2253cc:	bl	222118 <_ZN9SingletonI9DDSWorkerE11getInstanceEv>
  2253d0:	mov	x1, x19
  2253d4:	ldr	d8, [sp, #48]
  2253d8:	ldp	x19, x20, [sp, #16]
  2253dc:	ldp	x21, x22, [sp, #32]
  2253e0:	ldp	x29, x30, [sp], #64
  2253e4:	b	1b57e0 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE>
  2253e8:	bl	222118 <_ZN9SingletonI9DDSWorkerE11getInstanceEv>
  2253ec:	mov	x1, x19
  2253f0:	bl	1b54f0 <_ZN9DDSWorker9SendSteerERKN5drdds3msg5SteerE>
  2253f4:	bl	222118 <_ZN9SingletonI9DDSWorkerE11getInstanceEv>
  2253f8:	mov	x1, x19
  2253fc:	ldr	d8, [sp, #48]
  225400:	ldp	x19, x20, [sp, #16]
  225404:	ldp	x21, x22, [sp, #32]
  225408:	ldp	x29, x30, [sp], #64
  22540c:	b	1b57e0 <_ZN9DDSWorker15SendHandleSteerERKN5drdds3msg5SteerE>
  225410:	mov	x0, x19
  225414:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225418:	bl	aa010 <_ZN5drdds3msg10SteerValue1xEv@plt>
  22541c:	mov	x1, x0
  225420:	mov	x0, x19
  225424:	ldr	s8, [x1]
  225428:	fneg	s8, s8
  22542c:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225430:	bl	aa010 <_ZN5drdds3msg10SteerValue1xEv@plt>
  225434:	mov	x1, x0
  225438:	mov	x0, x19
  22543c:	str	s8, [x1]
  225440:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  225444:	bl	a8d40 <_ZN5drdds3msg10SteerValue1yEv@plt>
  225448:	mov	x1, x0
  22544c:	mov	x0, x19
  225450:	ldr	s8, [x1]
  225454:	fneg	s8, s8
  225458:	bl	a6950 <_ZN5drdds3msg5Steer4dataEv@plt>
  22545c:	bl	a8d40 <_ZN5drdds3msg10SteerValue1yEv@plt>
  225460:	str	s8, [x0]
  225464:	b	2253c4 <_ZN10VelControl7sendVelERN5drdds3msg5SteerE+0x1b4>

0000000000225468 <_ZN10VelControl11sendRealVelERN5drdds3msg5SteerE>:
  225468:	ldr	w0, [x0, #184]
  22546c:	sub	w0, w0, #0x1
  225470:	cmp	w0, #0x2
  225474:	b.ls	22547c <_ZN10VelControl11sendRealVelERN5drdds3msg5SteerE+0x14>  // b.plast
  225478:	ret
  22547c:	stp	x29, x30, [sp, #-32]!
  225480:	mov	x29, sp
  225484:	str	x19, [sp, #16]
  225488:	mov	x19, x1
  22548c:	bl	222118 <_ZN9SingletonI9DDSWorkerE11getInstanceEv>
  225490:	mov	x1, x19
  225494:	ldr	x19, [sp, #16]
  225498:	ldp	x29, x30, [sp], #32
  22549c:	b	1b5668 <_ZN9DDSWorker13SendRealSteerERKN5drdds3msg5SteerE>
