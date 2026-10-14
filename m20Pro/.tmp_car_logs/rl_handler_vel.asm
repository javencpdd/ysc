  bcf60:	stp	x29, x30, [sp, #-0x90]!
  bcf64:	mov	x29, sp
  bcf68:	stp	x19, x20, [sp, #0x10]
  bcf6c:	mov	x19, x0
  bcf70:	mov	x20, x1
  bcf74:	adrp	x0, #0x218000
  bcf78:	ldr	x0, [x0, #0xe88]
  bcf7c:	ldr	x1, [x0]
  bcf80:	str	x1, [sp, #0x88]
  bcf84:	mov	x1, #0
  bcf88:	ldr	x0, [x19, #0x108]
  bcf8c:	cbz	x0, #0xbcf98
  bcf90:	ldrb	w0, [x0, #0x9a8]
  bcf94:	cbnz	w0, #0xbcfe4
  bcf98:	str	x21, [sp, #0x20]
  bcf9c:	stp	d8, d9, [sp, #0x30]
  bcfa0:	str	d10, [sp, #0x28]
  bcfa4:	adrp	x0, #0x218000
  bcfa8:	ldr	x0, [x0, #0x750]
  bcfac:	str	x0, [sp, #0x58]
  bcfb0:	strb	wzr, [sp, #0x60]
  bcfb4:	adrp	x1, #0x218000
  bcfb8:	ldr	x1, [x1, #0x478]
  bcfbc:	cbz	x1, #0xbcfcc
  bcfc0:	bl	#0x9dbf0
  bcfc4:	cmp	w0, #0x23
  bcfc8:	b.eq	#0xbd01c
  bcfcc:	mov	w0, #1
  bcfd0:	strb	w0, [sp, #0x60]
  bcfd4:	ldr	x21, [x19, #8]
  bcfd8:	mov	x0, x20
  bcfdc:	bl	#0x9e1a0
  bcfe0:	b	#0xbd020
  bcfe4:	adrp	x20, #0x1bc000
  bcfe8:	add	x20, x20, #0x7b8
  bcfec:	mov	x1, x20
  bcff0:	add	x0, x19, #0xd8
  bcff4:	bl	#0xb4880
  bcff8:	adrp	x19, #0x217000
  bcffc:	ldr	x19, [x19, #0xc78]
  bd000:	mov	x2, #0x2d
  bd004:	mov	x1, x20
  bd008:	mov	x0, x19
  bd00c:	bl	#0x9e610
  bd010:	mov	x0, x19
  bd014:	bl	#0x9e6f0
  bd018:	b	#0xbd4a8
  bd01c:	bl	#0x9d730
  bd020:	bl	#0x9f210
  bd024:	str	s0, [x21, #0x28]
  bd028:	ldr	x21, [x19, #8]
  bd02c:	mov	x0, x20
  bd030:	bl	#0x9e1a0
  bd034:	bl	#0x9f8e0
  bd038:	str	s0, [x21, #0x2c]
  bd03c:	ldr	x21, [x19, #8]
  bd040:	mov	x0, x20
  bd044:	bl	#0x9e1a0
  bd048:	bl	#0xa0290
  bd04c:	str	s0, [x21, #0x30]
  bd050:	ldr	x0, [x19, #0x18]
  bd054:	add	x0, x0, #0x10
  bd058:	ldar	w21, [x0]
  bd05c:	mov	x0, x20
  bd060:	bl	#0x9e1a0
  bd064:	bl	#0x9f210
  bd068:	fmov	s9, s0
  bd06c:	mov	x0, x20
  bd070:	bl	#0x9e1a0
  bd074:	bl	#0x9f8e0
  bd078:	fmov	s8, s0
  bd07c:	mov	x0, x20
  bd080:	bl	#0x9e1a0
  bd084:	bl	#0xa0290
  bd088:	fmov	s10, s0
  bd08c:	str	s9, [sp, #0x68]
  bd090:	str	s8, [sp, #0x6c]
  bd094:	mov	w0, #0x3003
  bd098:	cmp	w21, w0
  bd09c:	b.eq	#0xbd230
  bd0a0:	b.hi	#0xbd0c8
  bd0a4:	mov	w0, #0x1003
  bd0a8:	cmp	w21, w0
  bd0ac:	b.eq	#0xbd0e0
  bd0b0:	mov	w0, #0x3001
  bd0b4:	cmp	w21, w0
  bd0b8:	b.ne	#0xbd17c
  bd0bc:	mov	x0, x20
  bd0c0:	bl	#0x9e1a0
  bd0c4:	b	#0xbd190
  bd0c8:	mov	w0, #0x3005
  bd0cc:	cmp	w21, w0
  bd0d0:	b.ne	#0xbd17c
  bd0d4:	mov	x0, x20
  bd0d8:	bl	#0x9e1a0
  bd0dc:	b	#0xbd2d8
  bd0e0:	mov	x0, x20
  bd0e4:	bl	#0x9e1a0
  bd0e8:	bl	#0x9f210
  bd0ec:	fmov	s8, s0
  bd0f0:	mov	x0, x20
  bd0f4:	bl	#0x9e1a0
  bd0f8:	bl	#0x9f8e0
  bd0fc:	fabs	s1, s8
  bd100:	fcvt	d2, s1
  bd104:	adrp	x0, #0x1ca000
  bd108:	ldr	d3, [x0, #0xaa0]
  bd10c:	fcmpe	d2, d3
  bd110:	b.pl	#0xbd174
  bd114:	fabs	s3, s0
  bd118:	fcvt	d4, s3
  bd11c:	ldr	d5, [x0, #0xaa0]
  bd120:	fcmpe	d4, d5
  bd124:	b.pl	#0xbd174
  bd128:	adrp	x0, #0x1ca000
  bd12c:	ldr	d5, [x0, #0xa40]
  bd130:	fcmpe	d2, d5
  bd134:	b.ge	#0xbd140
  bd138:	fcmpe	d4, d5
  bd13c:	b.lt	#0xbd174
  bd140:	str	s1, [sp, #0x50]
  bd144:	str	s3, [sp, #0x54]
  bd148:	fcmpe	s3, s1
  bd14c:	b.gt	#0xbd188
  bd150:	add	x0, sp, #0x50
  bd154:	ldr	s1, [x0]
  bd158:	fcvt	d2, s1
  bd15c:	adrp	x0, #0x1ca000
  bd160:	ldr	d1, [x0, #0xaa0]
  bd164:	fdiv	d1, d1, d2
  bd168:	fcvt	s1, d1
  bd16c:	fmul	s8, s8, s1
  bd170:	fmul	s0, s0, s1
  bd174:	str	s8, [sp, #0x68]
  bd178:	str	s0, [sp, #0x6c]
  bd17c:	mov	w0, w21
  bd180:	bl	#0x16cbb0
  bd184:	b	#0xbd378
  bd188:	add	x0, sp, #0x54
  bd18c:	b	#0xbd154
  bd190:	bl	#0x9f210
  bd194:	fmov	s8, s0
  bd198:	mov	x0, x20
  bd19c:	bl	#0x9e1a0
  bd1a0:	bl	#0x9f8e0
  bd1a4:	fabs	s1, s8
  bd1a8:	fcvt	d2, s1
  bd1ac:	adrp	x0, #0x1ca000
  bd1b0:	ldr	d3, [x0, #0xaa0]
  bd1b4:	fcmpe	d2, d3
  bd1b8:	b.pl	#0xbd21c
  bd1bc:	fabs	s3, s0
  bd1c0:	fcvt	d4, s3
  bd1c4:	ldr	d5, [x0, #0xaa0]
  bd1c8:	fcmpe	d4, d5
  bd1cc:	b.pl	#0xbd21c
  bd1d0:	adrp	x0, #0x1ca000
  bd1d4:	ldr	d5, [x0, #0xa40]
  bd1d8:	fcmpe	d2, d5
  bd1dc:	b.ge	#0xbd1e8
  bd1e0:	fcmpe	d4, d5
  bd1e4:	b.lt	#0xbd21c
  bd1e8:	str	s1, [sp, #0x50]
  bd1ec:	str	s3, [sp, #0x54]
  bd1f0:	fcmpe	s3, s1
  bd1f4:	b.gt	#0xbd228
  bd1f8:	add	x0, sp, #0x50
  bd1fc:	ldr	s1, [x0]
  bd200:	fcvt	d2, s1
  bd204:	adrp	x0, #0x1ca000
  bd208:	ldr	d1, [x0, #0xaa0]
  bd20c:	fdiv	d1, d1, d2
  bd210:	fcvt	s1, d1
  bd214:	fmul	s8, s8, s1
  bd218:	fmul	s0, s0, s1
  bd21c:	str	s8, [sp, #0x68]
  bd220:	str	s0, [sp, #0x6c]
  bd224:	b	#0xbd17c
  bd228:	add	x0, sp, #0x54
  bd22c:	b	#0xbd1fc
  bd230:	mov	x0, x20
  bd234:	bl	#0x9e1a0
  bd238:	bl	#0x9f210
  bd23c:	fmov	s8, s0
  bd240:	mov	x0, x20
  bd244:	bl	#0x9e1a0
  bd248:	bl	#0x9f8e0
  bd24c:	fabs	s1, s8
  bd250:	fcvt	d2, s1
  bd254:	adrp	x0, #0x1ca000
  bd258:	ldr	d3, [x0, #0xaa0]
  bd25c:	fcmpe	d2, d3
  bd260:	b.pl	#0xbd2c4
  bd264:	fabs	s3, s0
  bd268:	fcvt	d4, s3
  bd26c:	ldr	d5, [x0, #0xaa0]
  bd270:	fcmpe	d4, d5
  bd274:	b.pl	#0xbd2c4
  bd278:	adrp	x0, #0x1ca000
  bd27c:	ldr	d5, [x0, #0xa40]
  bd280:	fcmpe	d2, d5
  bd284:	b.ge	#0xbd290
  bd288:	fcmpe	d4, d5
  bd28c:	b.lt	#0xbd2c4
  bd290:	str	s1, [sp, #0x50]
  bd294:	str	s3, [sp, #0x54]
  bd298:	fcmpe	s1, s3
  bd29c:	b.mi	#0xbd2d0
  bd2a0:	add	x0, sp, #0x50
  bd2a4:	ldr	s1, [x0]
  bd2a8:	fcvt	d2, s1
  bd2ac:	adrp	x0, #0x1ca000
  bd2b0:	ldr	d1, [x0, #0xaa0]
  bd2b4:	fdiv	d1, d1, d2
  bd2b8:	fcvt	s1, d1
  bd2bc:	fmul	s8, s8, s1
  bd2c0:	fmul	s0, s0, s1
  bd2c4:	str	s8, [sp, #0x68]
  bd2c8:	str	s0, [sp, #0x6c]
  bd2cc:	b	#0xbd17c
  bd2d0:	add	x0, sp, #0x54
  bd2d4:	b	#0xbd2a4
  bd2d8:	bl	#0x9f210
  bd2dc:	fmov	s8, s0
  bd2e0:	mov	x0, x20
  bd2e4:	bl	#0x9e1a0
  bd2e8:	bl	#0x9f8e0
  bd2ec:	fabs	s1, s8
  bd2f0:	fcvt	d2, s1
  bd2f4:	adrp	x0, #0x1ca000
  bd2f8:	ldr	d3, [x0, #0xaa0]
  bd2fc:	fcmpe	d2, d3
  bd300:	b.pl	#0xbd364
  bd304:	fabs	s3, s0
  bd308:	fcvt	d4, s3
  bd30c:	ldr	d5, [x0, #0xaa0]
  bd310:	fcmpe	d4, d5
  bd314:	b.pl	#0xbd364
  bd318:	adrp	x0, #0x1ca000
  bd31c:	ldr	d5, [x0, #0xa40]
  bd320:	fcmpe	d2, d5
  bd324:	b.ge	#0xbd330
  bd328:	fcmpe	d4, d5
  bd32c:	b.lt	#0xbd364
  bd330:	str	s1, [sp, #0x50]
  bd334:	str	s3, [sp, #0x54]
  bd338:	fcmpe	s1, s3
  bd33c:	b.mi	#0xbd370
  bd340:	add	x0, sp, #0x50
  bd344:	ldr	s1, [x0]
  bd348:	fcvt	d2, s1
  bd34c:	adrp	x0, #0x1ca000
  bd350:	ldr	d1, [x0, #0xaa0]
  bd354:	fdiv	d1, d1, d2
  bd358:	fcvt	s1, d1
  bd35c:	fmul	s8, s8, s1
  bd360:	fmul	s0, s0, s1
  bd364:	str	s8, [sp, #0x68]
  bd368:	str	s0, [sp, #0x6c]
  bd36c:	b	#0xbd17c
  bd370:	add	x0, sp, #0x54
  bd374:	b	#0xbd344
  bd378:	str	w0, [sp, #0x78]
  bd37c:	lsr	x0, x0, #0x20
  bd380:	str	w0, [sp, #0x7c]
  bd384:	str	w1, [sp, #0x80]
  bd388:	ldr	s1, [sp, #0x78]
  bd38c:	fcmpe	s1, #0.0
  bd390:	b.le	#0xbd420
  bd394:	ldr	s0, [sp, #0x68]
  bd398:	fdiv	s0, s0, s1
  bd39c:	str	s0, [sp, #0x4c]
  bd3a0:	fmov	s1, #-1.00000000
  bd3a4:	str	s1, [sp, #0x50]
  bd3a8:	fmov	s2, #1.00000000
  bd3ac:	str	s2, [sp, #0x54]
  bd3b0:	fcmpe	s0, s1
  bd3b4:	b.mi	#0xbd3c8
  bd3b8:	fcmpe	s0, s2
  bd3bc:	b.le	#0xbd418
  bd3c0:	add	x0, sp, #0x54
  bd3c4:	b	#0xbd3cc
  bd3c8:	add	x0, sp, #0x50
  bd3cc:	ldr	s0, [x0]
  bd3d0:	ldr	x0, [x19, #0x18]
  bd3d4:	str	s0, [x0, #0x20]
  bd3d8:	ldr	s1, [sp, #0x7c]
  bd3dc:	fcmpe	s1, #0.0
  bd3e0:	b.le	#0xbd47c
  bd3e4:	ldr	s0, [sp, #0x6c]
  bd3e8:	fdiv	s0, s0, s1
  bd3ec:	str	s0, [sp, #0x4c]
  bd3f0:	fmov	s1, #-1.00000000
  bd3f4:	str	s1, [sp, #0x50]
  bd3f8:	fmov	s2, #1.00000000
  bd3fc:	str	s2, [sp, #0x54]
  bd400:	fcmpe	s0, s1
  bd404:	b.mi	#0xbd428
  bd408:	fcmpe	s0, s2
  bd40c:	b.le	#0xbd474
  bd410:	add	x0, sp, #0x54
  bd414:	b	#0xbd42c
  bd418:	add	x0, sp, #0x4c
  bd41c:	b	#0xbd3cc
  bd420:	movi	v0.2s, #0
  bd424:	b	#0xbd3d0
  bd428:	add	x0, sp, #0x50
  bd42c:	ldr	s0, [x0]
  bd430:	ldr	x0, [x19, #0x18]
  bd434:	str	s0, [x0, #0x24]
  bd438:	ldr	s0, [sp, #0x80]
  bd43c:	fcmpe	s0, #0.0
  bd440:	b.le	#0xbd4d8
  bd444:	fdiv	s0, s10, s0
  bd448:	str	s0, [sp, #0x4c]
  bd44c:	fmov	s1, #-1.00000000
  bd450:	str	s1, [sp, #0x50]
  bd454:	fmov	s2, #1.00000000
  bd458:	str	s2, [sp, #0x54]
  bd45c:	fcmpe	s0, s1
  bd460:	b.mi	#0xbd484
  bd464:	fcmpe	s0, s2
  bd468:	b.le	#0xbd4d0
  bd46c:	add	x0, sp, #0x54
  bd470:	b	#0xbd488
  bd474:	add	x0, sp, #0x4c
  bd478:	b	#0xbd42c
  bd47c:	movi	v0.2s, #0
  bd480:	b	#0xbd430
  bd484:	add	x0, sp, #0x50
  bd488:	ldr	s0, [x0]
  bd48c:	ldr	x0, [x19, #0x18]
  bd490:	str	s0, [x0, #0x28]
  bd494:	ldrb	w0, [sp, #0x60]
  bd498:	cbnz	w0, #0xbd4e0
  bd49c:	ldr	x21, [sp, #0x20]
  bd4a0:	ldp	d8, d9, [sp, #0x30]
  bd4a4:	ldr	d10, [sp, #0x28]
  bd4a8:	adrp	x0, #0x218000
  bd4ac:	ldr	x0, [x0, #0xe88]
  bd4b0:	ldr	x1, [sp, #0x88]
  bd4b4:	ldr	x2, [x0]
  bd4b8:	subs	x1, x1, x2
  bd4bc:	mov	x2, #0
  bd4c0:	b.ne	#0xbd550
  bd4c4:	ldp	x19, x20, [sp, #0x10]
  bd4c8:	ldp	x29, x30, [sp], #0x90
  bd4cc:	ret	
  bd4d0:	add	x0, sp, #0x4c
  bd4d4:	b	#0xbd488
  bd4d8:	movi	v0.2s, #0
  bd4dc:	b	#0xbd48c
  bd4e0:	cbz	w0, #0xbd50c
  bd4e4:	ldr	x0, [sp, #0x58]
  bd4e8:	cbz	x0, #0xbd530
  bd4ec:	adrp	x1, #0x218000
  bd4f0:	ldr	x1, [x1, #0x478]
  bd4f4:	cbz	x1, #0xbd540
  bd4f8:	bl	#0x9ed80
  bd4fc:	ldr	x21, [sp, #0x20]
  bd500:	ldp	d8, d9, [sp, #0x30]
  bd504:	ldr	d10, [sp, #0x28]
  bd508:	b	#0xbd4a8
  bd50c:	mov	w0, #1
  bd510:	bl	#0x9d730
  bd514:	mov	x19, x0
  bd518:	ldrb	w0, [sp, #0x60]
  bd51c:	cbz	w0, #0xbd528
  bd520:	add	x0, sp, #0x58
  bd524:	bl	#0xbcf18
  bd528:	mov	x0, x19
  bd52c:	bl	#0x9dd30
  bd530:	ldr	x21, [sp, #0x20]
  bd534:	ldp	d8, d9, [sp, #0x30]
  bd538:	ldr	d10, [sp, #0x28]
  bd53c:	b	#0xbd4a8
  bd540:	ldr	x21, [sp, #0x20]
  bd544:	ldp	d8, d9, [sp, #0x30]
  bd548:	ldr	d10, [sp, #0x28]
  bd54c:	b	#0xbd4a8
  bd550:	str	x21, [sp, #0x20]
  bd554:	stp	d8, d9, [sp, #0x30]
  bd558:	str	d10, [sp, #0x28]
  bd55c:	bl	#0xa05b0
;; 384 instructions
