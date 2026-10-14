  bbad0:	stp	x29, x30, [sp, #-0x40]!
  bbad4:	mov	x29, sp
  bbad8:	stp	x19, x20, [sp, #0x10]
  bbadc:	stp	x21, x22, [sp, #0x20]
  bbae0:	mov	x19, x0
  bbae4:	mov	x20, x1
  bbae8:	mov	x21, x2
  bbaec:	adrp	x0, #0x218000
  bbaf0:	ldr	x0, [x0, #0xe88]
  bbaf4:	ldr	x1, [x0]
  bbaf8:	str	x1, [sp, #0x38]
  bbafc:	mov	x1, #0
  bbb00:	mov	x0, x20
  bbb04:	bl	#0x9e7e0
  bbb08:	cmp	w0, #0
  bbb0c:	b.le	#0xbbb74
  bbb10:	adrp	x0, #0x218000
  bbb14:	ldr	x0, [x0, #0x210]
  bbb18:	ldr	w0, [x0]
  bbb1c:	cmp	w0, #4
  bbb20:	b.eq	#0xbbb28
  bbb24:	cbnz	w0, #0xbbb74
  bbb28:	mov	w0, #1
  bbb2c:	strb	w0, [x19, #0x119]
  bbb30:	ldr	x0, [x19, #0x18]
  bbb34:	add	x0, x0, #0xc
  bbb38:	mov	w1, #0x64
  bbb3c:	stlr	w1, [x0]
  bbb40:	mov	x0, x20
  bbb44:	bl	#0x9e7e0
  bbb48:	adrp	x1, #0x217000
  bbb4c:	ldr	x1, [x1, #0xc50]
  bbb50:	str	w0, [x1]
  bbb54:	cmp	w0, #0xc8
  bbb58:	b.gt	#0xbbcbc
  bbb5c:	adrp	x0, #0x217000
  bbb60:	ldr	x0, [x0, #0xc50]
  bbb64:	ldr	w1, [x0]
  bbb68:	mov	x0, x21
  bbb6c:	bl	#0x9e560
  bbb70:	b	#0xbbba4
  bbb74:	mov	w1, #-1
  bbb78:	mov	x0, x21
  bbb7c:	bl	#0x9e560
  bbb80:	adrp	x0, #0x217000
  bbb84:	ldr	x0, [x0, #0xc50]
  bbb88:	mov	w1, #1
  bbb8c:	str	w1, [x0]
  bbb90:	strb	wzr, [x19, #0x119]
  bbb94:	ldr	x0, [x19, #0x18]
  bbb98:	add	x0, x0, #0xc
  bbb9c:	mov	w1, #4
  bbba0:	stlr	w1, [x0]
  bbba4:	mov	x0, x20
  bbba8:	bl	#0x9e7e0
  bbbac:	str	w0, [sp, #0x30]
  bbbb0:	ldr	x0, [x19, #0x18]
  bbbb4:	add	x0, x0, #0xc
  bbbb8:	ldar	w0, [x0]
  bbbbc:	str	w0, [sp, #0x34]
  bbbc0:	adrp	x21, #0x217000
  bbbc4:	ldr	x21, [x21, #0xc50]
  bbbc8:	add	x4, sp, #0x34
  bbbcc:	mov	x3, x21
  bbbd0:	add	x2, sp, #0x30
  bbbd4:	adrp	x1, #0x1bc000
  bbbd8:	add	x1, x1, #0x550
  bbbdc:	add	x0, x19, #0xa8
  bbbe0:	bl	#0xbb9f0
  bbbe4:	adrp	x22, #0x217000
  bbbe8:	ldr	x22, [x22, #0xc78]
  bbbec:	mov	x2, #0xc
  bbbf0:	adrp	x1, #0x1bc000
  bbbf4:	add	x1, x1, #0x588
  bbbf8:	mov	x0, x22
  bbbfc:	bl	#0x9e610
  bbc00:	mov	x0, x20
  bbc04:	bl	#0x9e7e0
  bbc08:	mov	w1, w0
  bbc0c:	mov	x0, x22
  bbc10:	bl	#0x9f080
  bbc14:	mov	x20, x0
  bbc18:	mov	x2, #0x10
  bbc1c:	adrp	x1, #0x1bc000
  bbc20:	add	x1, x1, #0x598
  bbc24:	bl	#0x9e610
  bbc28:	ldr	w1, [x21]
  bbc2c:	mov	x0, x20
  bbc30:	bl	#0x9f080
  bbc34:	mov	x20, x0
  bbc38:	mov	x2, #0x11
  bbc3c:	adrp	x1, #0x1bc000
  bbc40:	add	x1, x1, #0x5b0
  bbc44:	bl	#0x9e610
  bbc48:	ldr	x0, [x19, #0x18]
  bbc4c:	add	x0, x0, #0xc
  bbc50:	ldar	w1, [x0]
  bbc54:	mov	w1, w1
  bbc58:	mov	x0, x20
  bbc5c:	bl	#0x9d850
  bbc60:	mov	x19, x0
  bbc64:	ldr	x0, [x0]
  bbc68:	ldur	x0, [x0, #-0x18]
  bbc6c:	add	x0, x19, x0
  bbc70:	ldr	x20, [x0, #0xf0]
  bbc74:	cbz	x20, #0xbbcd0
  bbc78:	ldrb	w0, [x20, #0x38]
  bbc7c:	cbz	w0, #0xbbcd4
  bbc80:	ldrb	w1, [x20, #0x43]
  bbc84:	mov	x0, x19
  bbc88:	bl	#0x9f6d0
  bbc8c:	bl	#0x9f530
  bbc90:	adrp	x0, #0x218000
  bbc94:	ldr	x0, [x0, #0xe88]
  bbc98:	ldr	x1, [sp, #0x38]
  bbc9c:	ldr	x2, [x0]
  bbca0:	subs	x1, x1, x2
  bbca4:	mov	x2, #0
  bbca8:	b.ne	#0xbbcf8
  bbcac:	ldp	x19, x20, [sp, #0x10]
  bbcb0:	ldp	x21, x22, [sp, #0x20]
  bbcb4:	ldp	x29, x30, [sp], #0x40
  bbcb8:	ret	
  bbcbc:	adrp	x0, #0x217000
  bbcc0:	ldr	x0, [x0, #0xc50]
  bbcc4:	mov	w1, #0xc8
  bbcc8:	str	w1, [x0]
  bbccc:	b	#0xbbb5c
  bbcd0:	bl	#0x9d520
  bbcd4:	mov	x0, x20
  bbcd8:	bl	#0x9d7d0
  bbcdc:	ldr	x0, [x20]
  bbce0:	ldr	x2, [x0, #0x30]
  bbce4:	mov	w1, #0xa
  bbce8:	mov	x0, x20
  bbcec:	blr	x2
  bbcf0:	and	w1, w0, #0xff
  bbcf4:	b	#0xbbc84
  bbcf8:	bl	#0xa05b0
;; 139 instructions
