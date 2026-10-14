  bd560:	stp	x29, x30, [sp, #-0x50]!
  bd564:	mov	x29, sp
  bd568:	stp	x19, x20, [sp, #0x10]
  bd56c:	str	x21, [sp, #0x20]
  bd570:	mov	x19, x0
  bd574:	mov	x20, x1
  bd578:	adrp	x0, #0x218000
  bd57c:	ldr	x0, [x0, #0xe88]
  bd580:	ldr	x1, [x0]
  bd584:	str	x1, [sp, #0x48]
  bd588:	mov	x1, #0
  bd58c:	adrp	x0, #0x218000
  bd590:	ldr	x0, [x0, #0x750]
  bd594:	str	x0, [sp, #0x38]
  bd598:	strb	wzr, [sp, #0x40]
  bd59c:	adrp	x1, #0x218000
  bd5a0:	ldr	x1, [x1, #0x478]
  bd5a4:	cbz	x1, #0xbd5b4
  bd5a8:	bl	#0x9dbf0
  bd5ac:	cmp	w0, #0x23
  bd5b0:	b.eq	#0xbd5c8
  bd5b4:	mov	w0, #1
  bd5b8:	strb	w0, [sp, #0x40]
  bd5bc:	mov	x0, x20
  bd5c0:	bl	#0x9e1a0
  bd5c4:	b	#0xbd5cc
  bd5c8:	bl	#0x9d730
  bd5cc:	ldr	x21, [x19, #0x18]
  bd5d0:	bl	#0x9f210
  bd5d4:	str	s0, [x21, #0x20]
  bd5d8:	mov	x0, x20
  bd5dc:	bl	#0x9e1a0
  bd5e0:	ldr	x21, [x19, #0x18]
  bd5e4:	bl	#0x9f8e0
  bd5e8:	str	s0, [x21, #0x24]
  bd5ec:	mov	x0, x20
  bd5f0:	bl	#0x9e1a0
  bd5f4:	ldr	x21, [x19, #0x18]
  bd5f8:	bl	#0xa0290
  bd5fc:	str	s0, [x21, #0x28]
  bd600:	ldr	x21, [x19, #8]
  bd604:	ldr	w1, [x21, #4]
  bd608:	mov	w0, #0x3001
  bd60c:	cmp	w1, w0
  bd610:	b.eq	#0xbd690
  bd614:	ldr	x0, [x19, #8]
  bd618:	ldr	w0, [x0, #4]
  bd61c:	mov	w1, #0xf001
  bd620:	cmp	w0, w1
  bd624:	b.eq	#0xbd850
  bd628:	b.ls	#0xbd6f4
  bd62c:	mov	w1, #0xf002
  bd630:	cmp	w0, w1
  bd634:	b.eq	#0xbd944
  bd638:	mov	w1, #0xf003
  bd63c:	cmp	w0, w1
  bd640:	b.ne	#0xbd770
  bd644:	ldr	x0, [x19, #0x18]
  bd648:	str	wzr, [x0, #0x20]
  bd64c:	ldr	x0, [x19, #0x18]
  bd650:	str	wzr, [x0, #0x24]
  bd654:	ldr	x0, [x19, #0x18]
  bd658:	str	wzr, [x0, #0x28]
  bd65c:	ldr	x0, [x19, #0x18]
  bd660:	str	wzr, [x0, #0x68]
  bd664:	ldr	x0, [x19, #0x18]
  bd668:	str	wzr, [x0, #0x6c]
  bd66c:	ldr	x0, [x19, #0x18]
  bd670:	str	wzr, [x0, #0x5c]
  bd674:	ldr	x0, [x19, #0x18]
  bd678:	str	wzr, [x0, #0x60]
  bd67c:	ldr	x0, [x19, #0x18]
  bd680:	str	wzr, [x0, #0x58]
  bd684:	mov	x0, x20
  bd688:	bl	#0x9e1a0
  bd68c:	b	#0xbd910
  bd690:	mov	x0, x20
  bd694:	bl	#0x9e1a0
  bd698:	bl	#0x9f210
  bd69c:	fmov	s1, #0.50000000
  bd6a0:	fmul	s0, s0, s1
  bd6a4:	str	s0, [x21, #0x28]
  bd6a8:	ldr	x21, [x19, #8]
  bd6ac:	mov	x0, x20
  bd6b0:	bl	#0x9e1a0
  bd6b4:	bl	#0x9f8e0
  bd6b8:	fcvt	d0, s0
  bd6bc:	mov	x0, #0x3333333333333333
  bd6c0:	movk	x0, #0x3fd3, lsl #48
  bd6c4:	fmov	d1, x0
  bd6c8:	fmul	d0, d0, d1
  bd6cc:	fcvt	s0, d0
  bd6d0:	str	s0, [x21, #0x2c]
  bd6d4:	ldr	x21, [x19, #8]
  bd6d8:	mov	x0, x20
  bd6dc:	bl	#0x9e1a0
  bd6e0:	bl	#0xa0290
  bd6e4:	fmov	s1, #0.50000000
  bd6e8:	fmul	s0, s0, s1
  bd6ec:	str	s0, [x21, #0x30]
  bd6f0:	b	#0xbd614
  bd6f4:	mov	w1, #0x3002
  bd6f8:	cmp	w0, w1
  bd6fc:	b.eq	#0xbd740
  bd700:	mov	w1, #0x3004
  bd704:	cmp	w0, w1
  bd708:	b.ne	#0xbd770
  bd70c:	ldr	x0, [x19, #0x18]
  bd710:	str	wzr, [x0, #0x20]
  bd714:	ldr	x0, [x19, #0x18]
  bd718:	str	wzr, [x0, #0x24]
  bd71c:	ldr	x0, [x19, #0x18]
  bd720:	str	wzr, [x0, #0x28]
  bd724:	ldr	x0, [x19, #0x18]
  bd728:	str	wzr, [x0, #0x68]
  bd72c:	ldr	x0, [x19, #0x18]
  bd730:	str	wzr, [x0, #0x6c]
  bd734:	mov	x0, x20
  bd738:	bl	#0x9e1a0
  bd73c:	b	#0xbd7ac
  bd740:	mov	x0, x20
  bd744:	bl	#0x9e1a0
  bd748:	bl	#0x9eb80
  bd74c:	fneg	s0, s0
  bd750:	str	s0, [sp, #0x30]
  bd754:	str	wzr, [sp, #0x34]
  bd758:	fcmpe	s0, #0.0
  bd75c:	b.mi	#0xbd7a4
  bd760:	add	x1, sp, #0x30
  bd764:	ldr	x0, [x19, #0x18]
  bd768:	ldr	s0, [x1]
  bd76c:	str	s0, [x0, #0x64]
  bd770:	ldrb	w0, [sp, #0x40]
  bd774:	cbnz	w0, #0xbd9c0
  bd778:	adrp	x0, #0x218000
  bd77c:	ldr	x0, [x0, #0xe88]
  bd780:	ldr	x1, [sp, #0x48]
  bd784:	ldr	x2, [x0]
  bd788:	subs	x1, x1, x2
  bd78c:	mov	x2, #0
  bd790:	b.ne	#0xbda04
  bd794:	ldp	x19, x20, [sp, #0x10]
  bd798:	ldr	x21, [sp, #0x20]
  bd79c:	ldp	x29, x30, [sp], #0x50
  bd7a0:	ret	
  bd7a4:	add	x1, sp, #0x34
  bd7a8:	b	#0xbd764
  bd7ac:	bl	#0xa0290
  bd7b0:	ldr	x0, [x19, #0x18]
  bd7b4:	fmov	s1, #7.00000000
  bd7b8:	fmul	s0, s0, s1
  bd7bc:	str	s0, [x0, #0x58]
  bd7c0:	mov	x0, x20
  bd7c4:	bl	#0x9e1a0
  bd7c8:	bl	#0x9f210
  bd7cc:	ldr	x0, [x19, #0x18]
  bd7d0:	fmov	s1, #11.00000000
  bd7d4:	fnmul	s0, s0, s1
  bd7d8:	str	s0, [x0, #0x5c]
  bd7dc:	mov	x0, x20
  bd7e0:	bl	#0x9e1a0
  bd7e4:	bl	#0x9f8e0
  bd7e8:	ldr	x0, [x19, #0x18]
  bd7ec:	mov	w1, #0x41040000
  bd7f0:	fmov	s1, w1
  bd7f4:	fnmul	s0, s0, s1
  bd7f8:	str	s0, [x0, #0x60]
  bd7fc:	mov	x0, x20
  bd800:	bl	#0x9e1a0
  bd804:	bl	#0x9eb80
  bd808:	fneg	s0, s0
  bd80c:	str	s0, [sp, #0x30]
  bd810:	str	wzr, [sp, #0x34]
  bd814:	fcmpe	s0, #0.0
  bd818:	b.mi	#0xbd848
  bd81c:	add	x1, sp, #0x30
  bd820:	ldr	x0, [x19, #0x18]
  bd824:	ldr	s0, [x1]
  bd828:	str	s0, [x0, #0x64]
  bd82c:	ldr	x0, [x19, #0x18]
  bd830:	ldr	s1, [x0, #0x64]
  bd834:	fmov	s0, #1.00000000
  bd838:	fcmpe	s1, s0
  bd83c:	b.le	#0xbd770
  bd840:	str	s0, [x0, #0x64]
  bd844:	b	#0xbd770
  bd848:	add	x1, sp, #0x34
  bd84c:	b	#0xbd820
  bd850:	ldr	x0, [x19, #0x18]
  bd854:	str	wzr, [x0, #0x20]
  bd858:	ldr	x0, [x19, #0x18]
  bd85c:	str	wzr, [x0, #0x24]
  bd860:	ldr	x0, [x19, #0x18]
  bd864:	str	wzr, [x0, #0x28]
  bd868:	mov	x0, x20
  bd86c:	bl	#0x9e1a0
  bd870:	ldr	x21, [x19, #0x18]
  bd874:	bl	#0xa00e0
  bd878:	str	s0, [x21, #0x68]
  bd87c:	mov	x0, x20
  bd880:	bl	#0x9e1a0
  bd884:	ldr	x21, [x19, #0x18]
  bd888:	bl	#0x9ce80
  bd88c:	str	s0, [x21, #0x6c]
  bd890:	mov	x0, x20
  bd894:	bl	#0x9e1a0
  bd898:	bl	#0x9f210
  bd89c:	ldr	x0, [x19, #0x18]
  bd8a0:	fneg	s0, s0
  bd8a4:	str	s0, [x0, #0x5c]
  bd8a8:	mov	x0, x20
  bd8ac:	bl	#0x9e1a0
  bd8b0:	bl	#0x9f8e0
  bd8b4:	ldr	x0, [x19, #0x18]
  bd8b8:	fneg	s0, s0
  bd8bc:	str	s0, [x0, #0x60]
  bd8c0:	mov	x0, x20
  bd8c4:	bl	#0x9e1a0
  bd8c8:	ldr	x21, [x19, #0x18]
  bd8cc:	bl	#0xa0290
  bd8d0:	str	s0, [x21, #0x58]
  bd8d4:	mov	x0, x20
  bd8d8:	bl	#0x9e1a0
  bd8dc:	bl	#0x9eb80
  bd8e0:	fneg	s0, s0
  bd8e4:	str	s0, [sp, #0x30]
  bd8e8:	str	wzr, [sp, #0x34]
  bd8ec:	fcmpe	s0, #0.0
  bd8f0:	b.mi	#0xbd908
  bd8f4:	add	x1, sp, #0x30
  bd8f8:	ldr	x0, [x19, #0x18]
  bd8fc:	ldr	s0, [x1]
  bd900:	str	s0, [x0, #0x64]
  bd904:	b	#0xbd770
  bd908:	add	x1, sp, #0x34
  bd90c:	b	#0xbd8f8
  bd910:	bl	#0x9eb80
  bd914:	fneg	s0, s0
  bd918:	str	s0, [sp, #0x30]
  bd91c:	str	wzr, [sp, #0x34]
  bd920:	fcmpe	s0, #0.0
  bd924:	b.mi	#0xbd93c
  bd928:	add	x1, sp, #0x30
  bd92c:	ldr	x0, [x19, #0x18]
  bd930:	ldr	s0, [x1]
  bd934:	str	s0, [x0, #0x64]
  bd938:	b	#0xbd770
  bd93c:	add	x1, sp, #0x34
  bd940:	b	#0xbd92c
  bd944:	mov	x0, x20
  bd948:	bl	#0x9e1a0
  bd94c:	ldr	x21, [x19, #0x18]
  bd950:	bl	#0xa00e0
  bd954:	str	s0, [x21, #0x68]
  bd958:	mov	x0, x20
  bd95c:	bl	#0x9e1a0
  bd960:	ldr	x21, [x19, #0x18]
  bd964:	bl	#0x9ce80
  bd968:	str	s0, [x21, #0x6c]
  bd96c:	ldr	x0, [x19, #0x18]
  bd970:	str	wzr, [x0, #0x5c]
  bd974:	ldr	x0, [x19, #0x18]
  bd978:	str	wzr, [x0, #0x60]
  bd97c:	ldr	x0, [x19, #0x18]
  bd980:	str	wzr, [x0, #0x58]
  bd984:	mov	x0, x20
  bd988:	bl	#0x9e1a0
  bd98c:	bl	#0x9eb80
  bd990:	fneg	s0, s0
  bd994:	str	s0, [sp, #0x30]
  bd998:	str	wzr, [sp, #0x34]
  bd99c:	fcmpe	s0, #0.0
  bd9a0:	b.mi	#0xbd9b8
  bd9a4:	add	x1, sp, #0x30
  bd9a8:	ldr	x0, [x19, #0x18]
  bd9ac:	ldr	s0, [x1]
  bd9b0:	str	s0, [x0, #0x64]
  bd9b4:	b	#0xbd770
  bd9b8:	add	x1, sp, #0x34
  bd9bc:	b	#0xbd9a8
  bd9c0:	cbz	w0, #0xbd9e0
  bd9c4:	ldr	x0, [sp, #0x38]
  bd9c8:	cbz	x0, #0xbd778
  bd9cc:	adrp	x1, #0x218000
  bd9d0:	ldr	x1, [x1, #0x478]
  bd9d4:	cbz	x1, #0xbd778
  bd9d8:	bl	#0x9ed80
  bd9dc:	b	#0xbd778
  bd9e0:	mov	w0, #1
  bd9e4:	bl	#0x9d730
  bd9e8:	mov	x19, x0
  bd9ec:	ldrb	w0, [sp, #0x40]
  bd9f0:	cbz	w0, #0xbd9fc
  bd9f4:	add	x0, sp, #0x38
  bd9f8:	bl	#0xbcf18
  bd9fc:	mov	x0, x19
  bda00:	bl	#0x9dd30
  bda04:	bl	#0xa05b0
;; 298 instructions
