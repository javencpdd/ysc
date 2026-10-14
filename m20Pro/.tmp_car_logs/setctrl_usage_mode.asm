  226078:	stp	x29, x30, [sp, #-0x60]!
  22607c:	mov	x29, sp
  226080:	stp	x21, x22, [sp, #0x20]
  226084:	adrp	x22, #0x2d2000
  226088:	ldr	x2, [x22, #0xfd0]
  22608c:	stp	x19, x20, [sp, #0x10]
  226090:	mov	x19, x0
  226094:	ldr	x3, [x2]
  226098:	str	x3, [sp, #0x58]
  22609c:	mov	x3, #0
  2260a0:	ldr	w0, [x0, #0xb8]
  2260a4:	str	w1, [sp, #0x4c]
  2260a8:	cmp	w0, w1
  2260ac:	b.eq	#0x226170
  2260b0:	stp	x23, x24, [sp, #0x30]
  2260b4:	bl	#0x222118
  2260b8:	ldr	w1, [sp, #0x4c]
  2260bc:	mov	x20, x0
  2260c0:	cmp	w1, #1
  2260c4:	b.ne	#0x226198
  2260c8:	adrp	x21, #0x2d2000
  2260cc:	add	x23, x19, #0x88
  2260d0:	ldr	x0, [x21, #0xf08]
  2260d4:	cbz	x0, #0x2260e4
  2260d8:	mov	x0, x23
  2260dc:	bl	#0xa8970
  2260e0:	cbnz	w0, #0x226318
  2260e4:	ldr	x0, [x19, #0x78]
  2260e8:	add	x2, sp, #0x4c
  2260ec:	adrp	x1, #0x250000
  2260f0:	add	x1, x1, #0x6f0
  2260f4:	bl	#0x227028
  2260f8:	ldr	w0, [sp, #0x4c]
  2260fc:	cmp	w0, #3
  226100:	b.eq	#0x2261fc
  226104:	ldr	w1, [x19, #0xb8]
  226108:	cmp	w1, #3
  22610c:	b.eq	#0x2263fc
  226110:	cmp	w0, #1
  226114:	b.ne	#0x226280
  226118:	add	x0, x20, #8
  22611c:	mov	w1, #0x10001
  226120:	bl	#0x1c85b0
  226124:	mov	x0, x20
  226128:	mov	w1, #1
  22612c:	bl	#0x1b8c08
  226130:	mov	x0, x20
  226134:	mov	w1, #0
  226138:	bl	#0x1bb4b0
  22613c:	mov	x0, x20
  226140:	mov	w1, #0
  226144:	bl	#0x1baf78
  226148:	mov	x0, x20
  22614c:	mov	w1, #0
  226150:	bl	#0x1b8990
  226154:	ldr	x21, [x21, #0xf08]
  226158:	ldr	w0, [sp, #0x4c]
  22615c:	str	w0, [x19, #0xb8]
  226160:	cbnz	x21, #0x226270
  226164:	nop	
  226168:	ldp	x23, x24, [sp, #0x30]
  22616c:	nop	
  226170:	ldr	x0, [x22, #0xfd0]
  226174:	ldr	x1, [sp, #0x58]
  226178:	ldr	x2, [x0]
  22617c:	subs	x1, x1, x2
  226180:	mov	x2, #0
  226184:	b.ne	#0x226478
  226188:	ldp	x19, x20, [sp, #0x10]
  22618c:	ldp	x21, x22, [sp, #0x20]
  226190:	ldp	x29, x30, [sp], #0x60
  226194:	ret	
  226198:	adrp	x21, #0x2d4000
  22619c:	add	x0, x21, #0x90
  2261a0:	ldarb	w1, [x0]
  2261a4:	tbz	w1, #0, #0x2263a8
  2261a8:	adrp	x23, #0x2d4000
  2261ac:	add	x0, x23, #0x2b0
  2261b0:	bl	#0x20f2b0
  2261b4:	tst	w0, #0xff
  2261b8:	b.ne	#0x2263e0
  2261bc:	mov	x0, x20
  2261c0:	bl	#0x1b5980
  2261c4:	tst	w0, #0xff
  2261c8:	b.ne	#0x2260c8
  2261cc:	ldr	x0, [x19, #0x78]
  2261d0:	adrp	x1, #0x250000
  2261d4:	adrp	x21, #0x2d2000
  2261d8:	add	x1, x1, #0x680
  2261dc:	add	x23, x19, #0x88
  2261e0:	bl	#0xf49f8
  2261e4:	mov	x0, x20
  2261e8:	mov	w1, #2
  2261ec:	bl	#0x1baa98
  2261f0:	ldr	x0, [x21, #0xf08]
  2261f4:	cbnz	x0, #0x2260d8
  2261f8:	b	#0x2260e4
  2261fc:	ldr	w0, [x19, #0xb8]
  226200:	cmp	w0, #1
  226204:	b.eq	#0x226410
  226208:	add	x0, x20, #8
  22620c:	mov	w1, #0x10001
  226210:	bl	#0x1c85b0
  226214:	mov	w24, #0x3002
  226218:	mov	x0, x20
  22621c:	mov	w1, #1
  226220:	bl	#0x1b8dc0
  226224:	bl	#0x222118
  226228:	mov	w1, #1
  22622c:	bl	#0x1b65b8
  226230:	ldr	w4, [x19, #0xb8]
  226234:	add	x3, sp, #0x54
  226238:	ldr	x0, [x19, #0x78]
  22623c:	add	x2, sp, #0x50
  226240:	adrp	x1, #0x250000
  226244:	add	x1, x1, #0x708
  226248:	stp	w4, w24, [sp, #0x50]
  22624c:	bl	#0x1cbc78
  226250:	mov	w1, w24
  226254:	mov	x0, x19
  226258:	mov	w2, #0
  22625c:	bl	#0x225a18
  226260:	ldr	w0, [sp, #0x4c]
  226264:	ldr	x21, [x21, #0xf08]
  226268:	str	w0, [x19, #0xb8]
  22626c:	cbz	x21, #0x226168
  226270:	mov	x0, x23
  226274:	bl	#0xaa360
  226278:	ldp	x23, x24, [sp, #0x30]
  22627c:	b	#0x226170
  226280:	ldr	w1, [x19, #0xb8]
  226284:	cmp	w1, #1
  226288:	b.eq	#0x226410
  22628c:	cmp	w0, #2
  226290:	b.eq	#0x226340
  226294:	b.hi	#0x226334
  226298:	cbnz	w0, #0x226118
  22629c:	mov	x0, x20
  2262a0:	mov	w1, #0
  2262a4:	bl	#0x1bb4b0
  2262a8:	mov	x0, x20
  2262ac:	mov	w1, #0
  2262b0:	bl	#0x1baf78
  2262b4:	mov	w1, #0
  2262b8:	mov	x0, x20
  2262bc:	bl	#0x1b8990
  2262c0:	mov	x0, x20
  2262c4:	bl	#0x1b5980
  2262c8:	tst	w0, #0xff
  2262cc:	ldr	x0, [x19, #0x78]
  2262d0:	b.eq	#0x226424
  2262d4:	ldr	w4, [x19, #0xb8]
  2262d8:	add	x3, sp, #0x54
  2262dc:	add	x2, sp, #0x50
  2262e0:	mov	w20, #0x1001
  2262e4:	adrp	x1, #0x250000
  2262e8:	add	x1, x1, #0x708
  2262ec:	stp	w4, w20, [sp, #0x50]
  2262f0:	bl	#0x1cbc78
  2262f4:	mov	w1, w20
  2262f8:	mov	x0, x19
  2262fc:	mov	w2, #0
  226300:	bl	#0x225a18
  226304:	bl	#0x222118
  226308:	mov	w1, #0
  22630c:	bl	#0x1b65b8
  226310:	ldr	w0, [sp, #0x4c]
  226314:	b	#0x226264
  226318:	ldr	x0, [x19, #0x78]
  22631c:	add	x2, sp, #0x4c
  226320:	adrp	x1, #0x250000
  226324:	add	x1, x1, #0x6b8
  226328:	bl	#0x226f58
  22632c:	ldp	x23, x24, [sp, #0x30]
  226330:	b	#0x226170
  226334:	cmp	w0, #3
  226338:	b.ne	#0x226264
  22633c:	b	#0x226208
  226340:	add	x0, x20, #8
  226344:	mov	w1, #0x10001
  226348:	bl	#0x1c85b0
  22634c:	mov	w24, #0x1001
  226350:	mov	x0, x20
  226354:	mov	w1, #1
  226358:	bl	#0x1bb4b0
  22635c:	mov	x0, x20
  226360:	mov	w1, #1
  226364:	bl	#0x1baf78
  226368:	mov	x0, x20
  22636c:	mov	w1, #1
  226370:	bl	#0x1b8990
  226374:	ldr	w4, [x19, #0xb8]
  226378:	add	x3, sp, #0x54
  22637c:	ldr	x0, [x19, #0x78]
  226380:	add	x2, sp, #0x50
  226384:	adrp	x1, #0x250000
  226388:	add	x1, x1, #0x708
  22638c:	stp	w4, w24, [sp, #0x50]
  226390:	bl	#0x1cbc78
  226394:	mov	w1, w24
  226398:	mov	x0, x19
  22639c:	mov	w2, #0
  2263a0:	bl	#0x225a18
  2263a4:	b	#0x226304
  2263a8:	bl	#0xa99b0
  2263ac:	cbz	w0, #0x2261a8
  2263b0:	adrp	x24, #0x2d4000
  2263b4:	add	x0, x24, #0x98
  2263b8:	bl	#0x1fa9d8
  2263bc:	adrp	x0, #0x2d2000
  2263c0:	add	x1, x24, #0x98
  2263c4:	adrp	x2, #0x2d3000
  2263c8:	add	x2, x2, #8
  2263cc:	ldr	x0, [x0, #0xe40]
  2263d0:	bl	#0xaa9d0
  2263d4:	add	x0, x21, #0x90
  2263d8:	bl	#0xaa0a0
  2263dc:	b	#0x2261a8
  2263e0:	add	x0, x21, #0x90
  2263e4:	ldarb	w1, [x0]
  2263e8:	tbz	w1, #0, #0x226440
  2263ec:	add	x0, x23, #0x2b0
  2263f0:	mov	w1, #0xa328
  2263f4:	bl	#0x2184e8
  2263f8:	b	#0x2261bc
  2263fc:	mov	x0, x20
  226400:	mov	w1, #0
  226404:	bl	#0x1b8dc0
  226408:	ldr	w0, [sp, #0x4c]
  22640c:	b	#0x226110
  226410:	mov	x0, x20
  226414:	mov	w1, #0
  226418:	bl	#0x1b8c08
  22641c:	ldr	w0, [sp, #0x4c]
  226420:	b	#0x22628c
  226424:	ldr	w3, [x19, #0xb8]
  226428:	add	x2, sp, #0x54
  22642c:	adrp	x1, #0x250000
  226430:	add	x1, x1, #0x738
  226434:	str	w3, [sp, #0x54]
  226438:	bl	#0xf56e8
  22643c:	b	#0x226304
  226440:	bl	#0xa99b0
  226444:	cbz	w0, #0x2263ec
  226448:	adrp	x24, #0x2d4000
  22644c:	add	x0, x24, #0x98
  226450:	bl	#0x1fa9d8
  226454:	adrp	x0, #0x2d2000
  226458:	add	x1, x24, #0x98
  22645c:	adrp	x2, #0x2d3000
  226460:	add	x2, x2, #8
  226464:	ldr	x0, [x0, #0xe40]
  226468:	bl	#0xaa9d0
  22646c:	add	x0, x21, #0x90
  226470:	bl	#0xaa0a0
  226474:	b	#0x2263ec
  226478:	stp	x23, x24, [sp, #0x30]
  22647c:	bl	#0xab600
  226480:	mov	x19, x0
  226484:	add	x0, x21, #0x90
  226488:	bl	#0xa70e0
  22648c:	mov	x0, x19
  226490:	bl	#0xa7a60
  226494:	b	#0x226480
;; 264 instructions
