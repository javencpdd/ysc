  2269f8:	stp	x29, x30, [sp, #-0xa0]!
  2269fc:	mov	x29, sp
  226a00:	stp	x21, x22, [sp, #0x20]
  226a04:	adrp	x22, #0x2d2000
  226a08:	adrp	x21, #0x250000
  226a0c:	ldr	x2, [x22, #0xfd0]
  226a10:	stp	x19, x20, [sp, #0x10]
  226a14:	add	x20, sp, #0x78
  226a18:	ldr	x3, [x2]
  226a1c:	str	x3, [sp, #0x98]
  226a20:	mov	x3, #0
  226a24:	mov	x19, x0
  226a28:	add	x1, x21, #0x980
  226a2c:	mov	x0, x20
  226a30:	bl	#0x224810
  226a34:	mov	x1, x20
  226a38:	mov	x0, x19
  226a3c:	bl	#0x16d268
  226a40:	ldr	x0, [sp, #0x78]
  226a44:	add	x1, x20, #0x10
  226a48:	cmp	x0, x1
  226a4c:	b.eq	#0x226a54
  226a50:	bl	#0xa7460
  226a54:	add	x1, x21, #0x980
  226a58:	mov	x0, x20
  226a5c:	bl	#0x224810
  226a60:	mov	x0, #0x30
  226a64:	bl	#0xa9290
  226a68:	mov	x21, x0
  226a6c:	mov	x8, x0
  226a70:	bl	#0xa7fe0
  226a74:	ldp	x1, x2, [sp, #0x78]
  226a78:	add	x3, x21, #0x20
  226a7c:	str	x3, [x21, #0x10]
  226a80:	add	x0, x21, #0x10
  226a84:	add	x2, x1, x2
  226a88:	bl	#0x224730
  226a8c:	stp	x23, x24, [sp, #0x30]
  226a90:	add	x1, x20, #0x10
  226a94:	ldr	x0, [sp, #0x78]
  226a98:	str	x21, [x19, #0x78]
  226a9c:	cmp	x0, x1
  226aa0:	b.eq	#0x226aa8
  226aa4:	bl	#0xa7460
  226aa8:	add	x1, x19, #0x88
  226aac:	fmov	v0.2s, #1.00000000
  226ab0:	strb	wzr, [x19, #0x80]
  226ab4:	add	x23, x19, #0xc8
  226ab8:	str	wzr, [x19, #0x84]
  226abc:	mov	x0, x23
  226ac0:	stp	xzr, xzr, [x19, #0x88]
  226ac4:	stp	xzr, xzr, [x1, #0x10]
  226ac8:	stp	xzr, xzr, [x1, #0x20]
  226acc:	str	wzr, [x19, #0xb8]
  226ad0:	stur	d0, [x19, #0xbc]
  226ad4:	bl	#0xaa2f0
  226ad8:	strb	wzr, [x19, #0xf0]
  226adc:	adrp	x1, #0x250000
  226ae0:	str	wzr, [x19, #0xf4]
  226ae4:	add	x1, x1, #0x150
  226ae8:	strb	wzr, [x19, #0xf8]
  226aec:	mov	x0, x20
  226af0:	str	xzr, [x19, #0x100]
  226af4:	bl	#0x224810
  226af8:	ldrb	w0, [x19, #0x30]
  226afc:	mov	w1, #0
  226b00:	strb	wzr, [sp, #0x77]
  226b04:	cmp	w0, #0xa
  226b08:	ldr	x24, [sp, #0x78]
  226b0c:	b.eq	#0x226b7c
  226b10:	strb	w1, [x19, #0xf0]
  226b14:	add	x20, x20, #0x10
  226b18:	cmp	x24, x20
  226b1c:	b.eq	#0x226b28
  226b20:	mov	x0, x24
  226b24:	bl	#0xa7460
  226b28:	ldr	x0, [x19, #0x78]
  226b2c:	adrp	x1, #0x250000
  226b30:	add	x2, x19, #0xf0
  226b34:	add	x1, x1, #0x130
  226b38:	bl	#0x1c5110
  226b3c:	ldrb	w0, [x19, #0xf0]
  226b40:	cbnz	w0, #0x226b70
  226b44:	ldr	x22, [x22, #0xfd0]
  226b48:	ldr	x0, [sp, #0x98]
  226b4c:	ldr	x1, [x22]
  226b50:	subs	x0, x0, x1
  226b54:	mov	x1, #0
  226b58:	b.ne	#0x226d80
  226b5c:	ldp	x19, x20, [sp, #0x10]
  226b60:	ldp	x21, x22, [sp, #0x20]
  226b64:	ldp	x23, x24, [sp, #0x30]
  226b68:	ldp	x29, x30, [sp], #0xa0
  226b6c:	ret	
  226b70:	mov	w0, #2
  226b74:	str	w0, [x19, #0xf4]
  226b78:	b	#0x226b44
  226b7c:	ldr	x3, [x19, #0x38]
  226b80:	mov	x2, #0x6907
  226b84:	ldr	x1, [sp, #0x80]
  226b88:	mov	x0, x24
  226b8c:	movk	x2, #0xc70f, lsl #16
  226b90:	stp	x25, x26, [sp, #0x40]
  226b94:	stp	x27, x28, [sp, #0x50]
  226b98:	str	x3, [sp, #0x60]
  226b9c:	bl	#0xa73e0
  226ba0:	ldr	x3, [sp, #0x60]
  226ba4:	mov	x26, x0
  226ba8:	ldp	x0, x25, [x3]
  226bac:	udiv	x27, x26, x25
  226bb0:	msub	x27, x27, x25, x26
  226bb4:	ldr	x0, [x0, x27, lsl #3]
  226bb8:	cbz	x0, #0x226d60
  226bbc:	ldr	x21, [x0]
  226bc0:	ldr	x24, [sp, #0x78]
  226bc4:	cbz	x21, #0x226d50
  226bc8:	ldr	x4, [sp, #0x80]
  226bcc:	mov	x28, #0
  226bd0:	ldr	x1, [x21, #0x70]
  226bd4:	cbz	x4, #0x226c74
  226bd8:	cmp	x1, x26
  226bdc:	b.eq	#0x226c80
  226be0:	cbnz	x28, #0x226c04
  226be4:	ldr	x21, [x21]
  226be8:	cbz	x21, #0x226c00
  226bec:	ldr	x1, [x21, #0x70]
  226bf0:	udiv	x2, x1, x25
  226bf4:	msub	x2, x2, x25, x1
  226bf8:	cmp	x27, x2
  226bfc:	b.eq	#0x226bd8
  226c00:	cbz	x28, #0x226d50
  226c04:	mov	x2, #0x6907
  226c08:	mov	x0, x24
  226c0c:	mov	x1, x4
  226c10:	movk	x2, #0xc70f, lsl #16
  226c14:	str	x3, [sp, #0x60]
  226c18:	bl	#0xa73e0
  226c1c:	ldr	x3, [sp, #0x60]
  226c20:	mov	x25, x0
  226c24:	ldp	x0, x24, [x3]
  226c28:	udiv	x26, x25, x24
  226c2c:	msub	x26, x26, x24, x25
  226c30:	ldr	x0, [x0, x26, lsl #3]
  226c34:	cbz	x0, #0x226d74
  226c38:	ldp	x28, x27, [sp, #0x78]
  226c3c:	ldr	x21, [x0]
  226c40:	ldr	x1, [x21, #0x70]
  226c44:	cbnz	x27, #0x226cf4
  226c48:	b	#0x226d24
  226c4c:	ldr	x0, [x21, #0x10]
  226c50:	cbz	x0, #0x226cb0
  226c54:	cbnz	x28, #0x226c04
  226c58:	ldr	x21, [x21]
  226c5c:	cbz	x21, #0x226c00
  226c60:	ldr	x1, [x21, #0x70]
  226c64:	udiv	x0, x1, x25
  226c68:	msub	x0, x0, x25, x1
  226c6c:	cmp	x27, x0
  226c70:	b.ne	#0x226c00
  226c74:	cmp	x1, x26
  226c78:	b.ne	#0x226c54
  226c7c:	b	#0x226c4c
;; 162 instructions
