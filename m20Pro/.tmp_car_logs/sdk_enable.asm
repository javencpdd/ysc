
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000001bad10 <_ZN9DDSWorker9SDKEnableEj>:
  1bad10:	stp	x29, x30, [sp, #-176]!
  1bad14:	mov	x29, sp
  1bad18:	stp	x21, x22, [sp, #32]
  1bad1c:	adrp	x21, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
  1bad20:	stp	x19, x20, [sp, #16]
  1bad24:	mov	x19, x0
  1bad28:	ldr	x0, [x21, #4048]
  1bad2c:	str	w1, [sp, #76]
  1bad30:	ldr	x20, [x19, #2744]
  1bad34:	ldr	x1, [x0]
  1bad38:	str	x1, [sp, #168]
  1bad3c:	mov	x1, #0x0                   	// #0
  1bad40:	cbz	x20, 1bae30 <_ZN9DDSWorker9SDKEnableEj+0x120>
  1bad44:	ldr	x0, [x19, #560]
  1bad48:	add	x2, x20, #0xb8
  1bad4c:	adrp	x1, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1bad50:	add	x1, x1, #0x810
  1bad54:	bl	f53a8 <_ZN8DrLogger4infoIJRiEEEvPKcDpOT_>
  1bad58:	ldr	w0, [x20, #184]
  1bad5c:	cmp	w0, #0x1
  1bad60:	b.eq	1bad8c <_ZN9DDSWorker9SDKEnableEj+0x7c>  // b.none
  1bad64:	ldr	x0, [x21, #4048]
  1bad68:	ldr	x1, [sp, #168]
  1bad6c:	ldr	x2, [x0]
  1bad70:	subs	x1, x1, x2
  1bad74:	mov	x2, #0x0                   	// #0
  1bad78:	b.ne	1baef4 <_ZN9DDSWorker9SDKEnableEj+0x1e4>  // b.any
  1bad7c:	ldp	x19, x20, [sp, #16]
  1bad80:	ldp	x21, x22, [sp, #32]
  1bad84:	ldp	x29, x30, [sp], #176
  1bad88:	ret
  1bad8c:	add	x20, sp, #0x50
  1bad90:	add	x22, sp, #0x58
  1bad94:	mov	x0, x20
  1bad98:	stp	x23, x24, [sp, #48]
  1bad9c:	bl	a7fc0 <_ZN5drdds3srv19StdSrvInt32_RequestC1Ev@plt>
  1bada0:	mov	x0, x22
  1bada4:	bl	a7cb0 <_ZN5drdds3srv20StdSrvInt32_ResponseC1Ev@plt>
  1bada8:	ldr	w1, [sp, #76]
  1badac:	mov	x0, x20
  1badb0:	bl	ab560 <_ZN5drdds3srv19StdSrvInt32_Request7commandEi@plt>
  1badb4:	add	x23, sp, #0x60
  1badb8:	mov	x1, x20
  1badbc:	mov	x0, x23
  1badc0:	ldr	x24, [x19, #2744]
  1badc4:	bl	a7640 <_ZN5drdds3srv19StdSrvInt32_RequestC1ERKS1_@plt>
  1badc8:	mov	x0, x24
  1badcc:	mov	x2, x22
  1badd0:	mov	x1, x23
  1badd4:	mov	w3, #0x7d0                 	// #2000
  1badd8:	bl	a7af0 <_ZN18DrDDSClientChannelIN5drdds3srv29StdSrvInt32_RequestPubSubTypeENS1_30StdSrvInt32_ResponsePubSubTypeEE4CallENS1_19StdSrvInt32_RequestERNS1_20StdSrvInt32_ResponseEi@plt>
  1baddc:	mov	x0, x23
  1bade0:	bl	a7600 <_ZN5drdds3srv19StdSrvInt32_RequestD1Ev@plt>
  1bade4:	mov	x0, x22
  1bade8:	bl	a8040 <_ZN5drdds3srv20StdSrvInt32_Response6resultEv@plt>
  1badec:	ldr	w1, [x0]
  1badf0:	ldr	w2, [sp, #76]
  1badf4:	ldr	x3, [x19, #560]
  1badf8:	cmp	w2, w1
  1badfc:	ccmn	w1, #0x1, #0x4, ne  // ne = any
  1bae00:	mov	x0, x3
  1bae04:	b.ne	1baee0 <_ZN9DDSWorker9SDKEnableEj+0x1d0>  // b.any
  1bae08:	adrp	x1, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1bae0c:	add	x2, sp, #0x4c
  1bae10:	add	x1, x1, #0x830
  1bae14:	bl	1c4f70 <_ZN8DrLogger4infoIJRjEEEvPKcDpOT_>
  1bae18:	mov	x0, x22
  1bae1c:	bl	a8890 <_ZN5drdds3srv20StdSrvInt32_ResponseD1Ev@plt>
  1bae20:	mov	x0, x20
  1bae24:	bl	a7600 <_ZN5drdds3srv19StdSrvInt32_RequestD1Ev@plt>
  1bae28:	ldp	x23, x24, [sp, #48]
  1bae2c:	b	1bad64 <_ZN9DDSWorker9SDKEnableEj+0x54>
  1bae30:	adrp	x1, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1bae34:	add	x1, x1, #0x180
  1bae38:	add	x22, sp, #0x88
  1bae3c:	stp	x23, x24, [sp, #48]
  1bae40:	add	x23, sp, #0x68
  1bae44:	ldr	x3, [x1]
  1bae48:	add	x2, x22, #0x10
  1bae4c:	ldrb	w1, [x1, #8]
  1bae50:	add	x5, x23, #0x10
  1bae54:	str	x3, [sp, #152]
  1bae58:	mov	x4, #0x9                   	// #9
  1bae5c:	strb	wzr, [sp, #161]
  1bae60:	mov	x0, #0x230                 	// #560
  1bae64:	strb	w1, [x22, #24]
  1bae68:	stp	x5, xzr, [sp, #104]
  1bae6c:	strb	wzr, [sp, #120]
  1bae70:	stp	x2, x4, [sp, #136]
  1bae74:	bl	a9290 <_Znwm@plt>
  1bae78:	mov	x20, x0
  1bae7c:	mov	x2, x23
  1bae80:	mov	x1, x22
  1bae84:	mov	w3, #0x0                   	// #0
  1bae88:	bl	a9800 <_ZN18DrDDSClientChannelIN5drdds3srv29StdSrvInt32_RequestPubSubTypeENS1_30StdSrvInt32_ResponsePubSubTypeEEC1ENSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEESA_i@plt>
  1bae8c:	ldr	x0, [sp, #104]
  1bae90:	add	x23, x23, #0x10
  1bae94:	cmp	x0, x23
  1bae98:	b.eq	1baea0 <_ZN9DDSWorker9SDKEnableEj+0x190>  // b.none
  1bae9c:	bl	a7460 <_ZdlPv@plt>
  1baea0:	ldr	x0, [sp, #136]
  1baea4:	add	x22, x22, #0x10
  1baea8:	cmp	x0, x22
  1baeac:	b.eq	1baeb4 <_ZN9DDSWorker9SDKEnableEj+0x1a4>  // b.none
  1baeb0:	bl	a7460 <_ZdlPv@plt>
  1baeb4:	ldr	x22, [x19, #2744]
  1baeb8:	str	x20, [x19, #2744]
  1baebc:	cbz	x22, 1baed8 <_ZN9DDSWorker9SDKEnableEj+0x1c8>
  1baec0:	mov	x0, x22
  1baec4:	bl	a9e20 <_ZN18DrDDSClientChannelIN5drdds3srv29StdSrvInt32_RequestPubSubTypeENS1_30StdSrvInt32_ResponsePubSubTypeEED1Ev@plt>
  1baec8:	mov	x0, x22
  1baecc:	mov	x1, #0x230                 	// #560
  1baed0:	bl	a67e0 <_ZdlPvm@plt>
  1baed4:	ldr	x20, [x19, #2744]
  1baed8:	ldp	x23, x24, [sp, #48]
  1baedc:	b	1bad44 <_ZN9DDSWorker9SDKEnableEj+0x34>
  1baee0:	adrp	x1, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1baee4:	add	x2, sp, #0x4c
  1baee8:	add	x1, x1, #0x850
  1baeec:	bl	1c5040 <_ZN8DrLogger5errorIJRjEEEvPKcDpOT_>
  1baef0:	b	1bae18 <_ZN9DDSWorker9SDKEnableEj+0x108>
  1baef4:	stp	x23, x24, [sp, #48]
  1baef8:	bl	ab600 <__stack_chk_fail@plt>
  1baefc:	mov	x19, x0
  1baf00:	mov	x1, #0x230                 	// #560
  1baf04:	mov	x0, x20
  1baf08:	bl	a67e0 <_ZdlPvm@plt>
  1baf0c:	ldr	x0, [sp, #104]
  1baf10:	add	x23, x23, #0x10
  1baf14:	cmp	x0, x23
  1baf18:	b.eq	1baf20 <_ZN9DDSWorker9SDKEnableEj+0x210>  // b.none
  1baf1c:	bl	a7460 <_ZdlPv@plt>
  1baf20:	ldr	x0, [sp, #136]
  1baf24:	add	x22, x22, #0x10
  1baf28:	cmp	x0, x22
  1baf2c:	b.eq	1baf64 <_ZN9DDSWorker9SDKEnableEj+0x254>  // b.none
  1baf30:	bl	a7460 <_ZdlPv@plt>
  1baf34:	b	1baf64 <_ZN9DDSWorker9SDKEnableEj+0x254>
  1baf38:	mov	x19, x0
  1baf3c:	b	1baf0c <_ZN9DDSWorker9SDKEnableEj+0x1fc>
  1baf40:	mov	x19, x0
  1baf44:	b	1baf54 <_ZN9DDSWorker9SDKEnableEj+0x244>
  1baf48:	mov	x19, x0
  1baf4c:	mov	x0, x23
  1baf50:	bl	a7600 <_ZN5drdds3srv19StdSrvInt32_RequestD1Ev@plt>
  1baf54:	mov	x0, x22
  1baf58:	bl	a8890 <_ZN5drdds3srv20StdSrvInt32_ResponseD1Ev@plt>
  1baf5c:	mov	x0, x20
  1baf60:	bl	a7600 <_ZN5drdds3srv19StdSrvInt32_RequestD1Ev@plt>
  1baf64:	mov	x0, x19
  1baf68:	bl	a7a60 <_Unwind_Resume@plt>
  1baf6c:	mov	x19, x0
  1baf70:	b	1baf5c <_ZN9DDSWorker9SDKEnableEj+0x24c>
  1baf74:	nop

00000000001baf78 <_ZN9DDSWorker9LIOEnableEb>:
  1baf78:	stp	x29, x30, [sp, #-192]!
  1baf7c:	mov	x29, sp
  1baf80:	stp	x21, x22, [sp, #32]
  1baf84:	adrp	x21, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
  1baf88:	strb	w1, [sp, #95]
  1baf8c:	ldr	x1, [x21, #4048]
  1baf90:	stp	x19, x20, [sp, #16]
  1baf94:	mov	x19, x0
  1baf98:	ldr	x0, [x0, #2728]
  1baf9c:	ldr	x2, [x1]
  1bafa0:	str	x2, [sp, #184]
  1bafa4:	mov	x2, #0x0                   	// #0
  1bafa8:	cbz	x0, 1bb0d8 <_ZN9DDSWorker9LIOEnableEb+0x160>
  1bafac:	adrp	x20, 2d9000 <_ZN8eprosima8fastrtps5typesL14TKNAME_STRING8E+0x8>
  1bafb0:	add	x1, x20, #0xe70
  1bafb4:	ldrb	w0, [sp, #95]
  1bafb8:	ldrb	w1, [x1, #64]
  1bafbc:	cmp	w1, w0
  1bafc0:	b.eq	1bafe8 <_ZN9DDSWorker9LIOEnableEb+0x70>  // b.none
  1bafc4:	ldr	x0, [x19, #560]
  1bafc8:	adrp	x1, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1bafcc:	ldr	x22, [x19, #2728]
  1bafd0:	add	x1, x1, #0x870
  1bafd4:	add	x2, x22, #0xb8
  1bafd8:	bl	f53a8 <_ZN8DrLogger4infoIJRiEEEvPKcDpOT_>
  1bafdc:	ldr	w0, [x22, #184]
  1bafe0:	cmp	w0, #0x1
  1bafe4:	b.eq	1bb010 <_ZN9DDSWorker9LIOEnableEb+0x98>  // b.none
  1bafe8:	ldr	x0, [x21, #4048]
  1bafec:	ldr	x1, [sp, #184]
  1baff0:	ldr	x2, [x0]
  1baff4:	subs	x1, x1, x2
  1baff8:	mov	x2, #0x0                   	// #0
  1baffc:	b.ne	1bb184 <_ZN9DDSWorker9LIOEnableEb+0x20c>  // b.any
  1bb000:	ldp	x19, x20, [sp, #16]
  1bb004:	ldp	x21, x22, [sp, #32]
  1bb008:	ldp	x29, x30, [sp], #192
  1bb00c:	ret
  1bb010:	add	x22, sp, #0x60
  1bb014:	stp	x23, x24, [sp, #48]
  1bb018:	mov	x0, x22
  1bb01c:	add	x23, sp, #0x68
  1bb020:	str	x25, [sp, #64]
  1bb024:	bl	a7fc0 <_ZN5drdds3srv19StdSrvInt32_RequestC1Ev@plt>
  1bb028:	mov	x0, x23
  1bb02c:	bl	a7cb0 <_ZN5drdds3srv20StdSrvInt32_ResponseC1Ev@plt>
  1bb030:	ldrb	w1, [sp, #95]
  1bb034:	mov	x0, x22
  1bb038:	bl	ab560 <_ZN5drdds3srv19StdSrvInt32_Request7commandEi@plt>
  1bb03c:	add	x24, sp, #0x70
  1bb040:	mov	x1, x22
  1bb044:	mov	x0, x24
  1bb048:	ldr	x25, [x19, #2728]
  1bb04c:	bl	a7640 <_ZN5drdds3srv19StdSrvInt32_RequestC1ERKS1_@plt>
  1bb050:	mov	x0, x25
  1bb054:	mov	x2, x23
  1bb058:	mov	x1, x24
  1bb05c:	mov	w3, #0x7d0                 	// #2000
  1bb060:	bl	a7af0 <_ZN18DrDDSClientChannelIN5drdds3srv29StdSrvInt32_RequestPubSubTypeENS1_30StdSrvInt32_ResponsePubSubTypeEE4CallENS1_19StdSrvInt32_RequestERNS1_20StdSrvInt32_ResponseEi@plt>
  1bb064:	mov	x0, x24
  1bb068:	bl	a7600 <_ZN5drdds3srv19StdSrvInt32_RequestD1Ev@plt>
  1bb06c:	mov	x0, x23
  1bb070:	bl	a8040 <_ZN5drdds3srv20StdSrvInt32_Response6resultEv@plt>
  1bb074:	ldr	w1, [x0]
  1bb078:	ldr	x2, [x19, #560]
  1bb07c:	cmp	w1, #0x1
  1bb080:	b.eq	1bb0b4 <_ZN9DDSWorker9LIOEnableEb+0x13c>  // b.none
  1bb084:	mov	x0, x2
  1bb088:	adrp	x1, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1bb08c:	add	x2, sp, #0x5f
  1bb090:	add	x1, x1, #0x8b0
  1bb094:	bl	1c51e0 <_ZN8DrLogger5errorIJRbEEEvPKcDpOT_>
  1bb098:	mov	x0, x23
  1bb09c:	bl	a8890 <_ZN5drdds3srv20StdSrvInt32_ResponseD1Ev@plt>
  1bb0a0:	mov	x0, x22
  1bb0a4:	bl	a7600 <_ZN5drdds3srv19StdSrvInt32_RequestD1Ev@plt>
  1bb0a8:	ldp	x23, x24, [sp, #48]
  1bb0ac:	ldr	x25, [sp, #64]
  1bb0b0:	b	1bafe8 <_ZN9DDSWorker9LIOEnableEb+0x70>
  1bb0b4:	ldrb	w3, [sp, #95]
  1bb0b8:	add	x20, x20, #0xe70
  1bb0bc:	mov	x0, x2
  1bb0c0:	adrp	x1, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1bb0c4:	add	x2, sp, #0x5f
  1bb0c8:	add	x1, x1, #0x890
  1bb0cc:	strb	w3, [x20, #64]
  1bb0d0:	bl	1c5110 <_ZN8DrLogger4infoIJRbEEEvPKcDpOT_>
  1bb0d4:	b	1bb098 <_ZN9DDSWorker9LIOEnableEb+0x120>
  1bb0d8:	adrp	x0, 243000 <_ZTSZN15MotionModuleCLI5setupEvEUlvE0_+0x2b0>
  1bb0dc:	add	x0, x0, #0x158
  1bb0e0:	add	x20, sp, #0x98
  1bb0e4:	add	x22, sp, #0x78
  1bb0e8:	add	x1, x20, #0x10
  1bb0ec:	add	x4, x22, #0x10
  1bb0f0:	ldr	x2, [x0]
  1bb0f4:	str	x2, [sp, #168]
  1bb0f8:	ldur	w2, [x0, #7]
  1bb0fc:	mov	x3, #0xb                   	// #11
  1bb100:	strb	wzr, [sp, #179]
  1bb104:	mov	x0, #0x230                 	// #560
  1bb108:	stur	w2, [x20, #23]
  1bb10c:	stp	x4, xzr, [sp, #120]
  1bb110:	strb	wzr, [sp, #136]
  1bb114:	stp	x1, x3, [sp, #152]
  1bb118:	bl	a9290 <_Znwm@plt>
  1bb11c:	mov	x2, x22
  1bb120:	mov	x1, x20
  1bb124:	mov	w3, #0x0                   	// #0
  1bb128:	stp	x23, x24, [sp, #48]
  1bb12c:	mov	x23, x0
  1bb130:	bl	a9800 <_ZN18DrDDSClientChannelIN5drdds3srv29StdSrvInt32_RequestPubSubTypeENS1_30StdSrvInt32_ResponsePubSubTypeEEC1ENSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEESA_i@plt>
  1bb134:	ldr	x0, [sp, #120]
  1bb138:	add	x22, x22, #0x10
  1bb13c:	cmp	x0, x22
  1bb140:	b.eq	1bb148 <_ZN9DDSWorker9LIOEnableEb+0x1d0>  // b.none
  1bb144:	bl	a7460 <_ZdlPv@plt>
  1bb148:	ldr	x0, [sp, #152]
  1bb14c:	add	x20, x20, #0x10
  1bb150:	cmp	x0, x20
  1bb154:	b.eq	1bb15c <_ZN9DDSWorker9LIOEnableEb+0x1e4>  // b.none
  1bb158:	bl	a7460 <_ZdlPv@plt>
  1bb15c:	ldr	x20, [x19, #2728]
  1bb160:	str	x23, [x19, #2728]
  1bb164:	cbz	x20, 1bb17c <_ZN9DDSWorker9LIOEnableEb+0x204>
  1bb168:	mov	x0, x20
  1bb16c:	bl	a9e20 <_ZN18DrDDSClientChannelIN5drdds3srv29StdSrvInt32_RequestPubSubTypeENS1_30StdSrvInt32_ResponsePubSubTypeEED1Ev@plt>
  1bb170:	mov	x0, x20
  1bb174:	mov	x1, #0x230                 	// #560
  1bb178:	bl	a67e0 <_ZdlPvm@plt>
  1bb17c:	ldp	x23, x24, [sp, #48]
  1bb180:	b	1bafac <_ZN9DDSWorker9LIOEnableEb+0x34>
  1bb184:	stp	x23, x24, [sp, #48]
  1bb188:	str	x25, [sp, #64]
  1bb18c:	bl	ab600 <__stack_chk_fail@plt>
  1bb190:	mov	x19, x0
  1bb194:	mov	x1, #0x230                 	// #560
  1bb198:	mov	x0, x23
  1bb19c:	bl	a67e0 <_ZdlPvm@plt>
  1bb1a0:	ldr	x0, [sp, #120]
  1bb1a4:	str	x25, [sp, #64]
  1bb1a8:	add	x22, x22, #0x10
  1bb1ac:	cmp	x0, x22
  1bb1b0:	b.eq	1bb1b8 <_ZN9DDSWorker9LIOEnableEb+0x240>  // b.none
  1bb1b4:	bl	a7460 <_ZdlPv@plt>
  1bb1b8:	ldr	x0, [sp, #152]
  1bb1bc:	add	x20, x20, #0x10
  1bb1c0:	cmp	x0, x20
  1bb1c4:	b.eq	1bb208 <_ZN9DDSWorker9LIOEnableEb+0x290>  // b.none
  1bb1c8:	bl	a7460 <_ZdlPv@plt>
  1bb1cc:	b	1bb208 <_ZN9DDSWorker9LIOEnableEb+0x290>
  1bb1d0:	mov	x19, x0
  1bb1d4:	stp	x23, x24, [sp, #48]
  1bb1d8:	b	1bb1a0 <_ZN9DDSWorker9LIOEnableEb+0x228>
  1bb1dc:	mov	x19, x0
  1bb1e0:	b	1bb200 <_ZN9DDSWorker9LIOEnableEb+0x288>
  1bb1e4:	mov	x19, x0
  1bb1e8:	b	1bb1f8 <_ZN9DDSWorker9LIOEnableEb+0x280>
  1bb1ec:	mov	x19, x0
  1bb1f0:	mov	x0, x24
  1bb1f4:	bl	a7600 <_ZN5drdds3srv19StdSrvInt32_RequestD1Ev@plt>
  1bb1f8:	mov	x0, x23
  1bb1fc:	bl	a8890 <_ZN5drdds3srv20StdSrvInt32_ResponseD1Ev@plt>
