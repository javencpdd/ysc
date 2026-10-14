
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000000cc5a8 <_ZN9CmdHandle4initEv>:
   cc5a8:	a9b67bfd 	stp	x29, x30, [sp, #-160]!
   cc5ac:	f0000b01 	adrp	x1, 22f000 <_IO_stdin_used+0x530>
   cc5b0:	913aa021 	add	x1, x1, #0xea8
   cc5b4:	910003fd 	mov	x29, sp
   cc5b8:	a90573fb 	stp	x27, x28, [sp, #80]
   cc5bc:	d000103b 	adrp	x27, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   cc5c0:	f947eb62 	ldr	x2, [x27, #4048]
   cc5c4:	a90153f3 	stp	x19, x20, [sp, #16]
   cc5c8:	aa0003f3 	mov	x19, x0
   cc5cc:	f9407800 	ldr	x0, [x0, #240]
   cc5d0:	f9400043 	ldr	x3, [x2]
   cc5d4:	f9004fe3 	str	x3, [sp, #152]
   cc5d8:	d2800003 	mov	x3, #0x0                   	// #0
   cc5dc:	a9025bf5 	stp	x21, x22, [sp, #32]
   cc5e0:	a90363f7 	stp	x23, x24, [sp, #48]
   cc5e4:	a9046bf9 	stp	x25, x26, [sp, #64]
   cc5e8:	9400a104 	bl	f49f8 <_ZN8DrLogger4infoIJEEEvPKcDpOT_>
   cc5ec:	91002260 	add	x0, x19, #0x8
   cc5f0:	9400ccbc 	bl	ff8e0 <_ZN9heratBeat13initHeartBeatEv>
   cc5f4:	d2800100 	mov	x0, #0x8                   	// #8
   cc5f8:	97ff7326 	bl	a9290 <_Znwm@plt>
   cc5fc:	aa0003f5 	mov	x21, x0
   cc600:	d2800400 	mov	x0, #0x20                  	// #32
   cc604:	f90002bf 	str	xzr, [x21]
   cc608:	97ff7322 	bl	a9290 <_Znwm@plt>
   cc60c:	d0001022 	adrp	x2, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   cc610:	aa0003e3 	mov	x3, x0
   cc614:	b0000fc5 	adrp	x5, 2c5000 <__FRAME_END__+0x3e064>
   cc618:	f0000004 	adrp	x4, cf000 <_ZN9CmdHandleC1Ev+0x808>
   cc61c:	f9479c42 	ldr	x2, [x2, #3896]
   cc620:	911da0a5 	add	x5, x5, #0x768
   cc624:	91372084 	add	x4, x4, #0xdc8
   cc628:	a9004c65 	stp	x5, x19, [x3]
   cc62c:	910203f4 	add	x20, sp, #0x80
   cc630:	a9017c64 	stp	x4, xzr, [x3, #16]
   cc634:	aa1403e1 	mov	x1, x20
   cc638:	aa1503e0 	mov	x0, x21
   cc63c:	f90043e3 	str	x3, [sp, #128]
   cc640:	97ff701c 	bl	a86b0 <_ZNSt6thread15_M_start_threadESt10unique_ptrINS_6_StateESt14default_deleteIS1_EEPFvvE@plt>
   cc644:	f94043e0 	ldr	x0, [sp, #128]
   cc648:	b4000080 	cbz	x0, cc658 <_ZN9CmdHandle4initEv+0xb0>
   cc64c:	f9400001 	ldr	x1, [x0]
   cc650:	f9400421 	ldr	x1, [x1, #8]
   cc654:	d63f0020 	blr	x1
   cc658:	f940ca60 	ldr	x0, [x19, #400]
   cc65c:	f900ca75 	str	x21, [x19, #400]
   cc660:	b40000a0 	cbz	x0, cc674 <_ZN9CmdHandle4initEv+0xcc>
   cc664:	f9400001 	ldr	x1, [x0]
   cc668:	b5005361 	cbnz	x1, cd0d4 <_ZN9CmdHandle4initEv+0xb2c>
   cc66c:	d2800101 	mov	x1, #0x8                   	// #8
   cc670:	97ff685c 	bl	a67e0 <_ZdlPvm@plt>
   cc674:	d0000022 	adrp	x2, d2000 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE+0x3f8>
   cc678:	9103c042 	add	x2, x2, #0xf0
   cc67c:	91040276 	add	x22, x19, #0x100
   cc680:	9101e3f7 	add	x23, sp, #0x78
   cc684:	9101f3f5 	add	x21, sp, #0x7c
   cc688:	aa1703e1 	mov	x1, x23
   cc68c:	52800c98 	mov	w24, #0x64                  	// #100
   cc690:	aa1603e0 	mov	x0, x22
   cc694:	b9007bf8 	str	w24, [sp, #120]
   cc698:	52807d5a 	mov	w26, #0x3ea                 	// #1002
   cc69c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc6a0:	52800059 	mov	w25, #0x2                   	// #2
   cc6a4:	9000105c 	adrp	x28, 2d4000 <_ZZN9SingletonI15ExceptionHandleE11getInstanceEvE8instance+0x350>
   cc6a8:	f9004bf3 	str	x19, [sp, #144]
   cc6ac:	9400b9cb 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc6b0:	aa1503e1 	mov	x1, x21
   cc6b4:	b9007ff8 	str	w24, [sp, #124]
   cc6b8:	9400b2d2 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc6bc:	528089b8 	mov	w24, #0x44d                 	// #1101
   cc6c0:	aa1403e1 	mov	x1, x20
   cc6c4:	9400a0ff 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc6c8:	d0000022 	adrp	x2, d2000 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE+0x3f8>
   cc6cc:	910b4042 	add	x2, x2, #0x2d0
   cc6d0:	aa1703e1 	mov	x1, x23
   cc6d4:	aa1603e0 	mov	x0, x22
   cc6d8:	b9007bfa 	str	w26, [sp, #120]
   cc6dc:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc6e0:	f9004bf3 	str	x19, [sp, #144]
   cc6e4:	9400b9bd 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc6e8:	aa1503e1 	mov	x1, x21
   cc6ec:	b9007ff9 	str	w25, [sp, #124]
   cc6f0:	9400b2c4 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc6f4:	aa1403e1 	mov	x1, x20
   cc6f8:	9400a0f2 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc6fc:	90000022 	adrp	x2, d0000 <_ZN9CmdHandle12UploadThreadEv+0x238>
   cc700:	912a0042 	add	x2, x2, #0xa80
   cc704:	aa1703e1 	mov	x1, x23
   cc708:	aa1603e0 	mov	x0, x22
   cc70c:	b9007bfa 	str	w26, [sp, #120]
   cc710:	5280003a 	mov	w26, #0x1                   	// #1
   cc714:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc718:	f9004bf3 	str	x19, [sp, #144]
   cc71c:	9400b9af 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc720:	52800062 	mov	w2, #0x3                   	// #3
   cc724:	aa1503e1 	mov	x1, x21
   cc728:	b9007fe2 	str	w2, [sp, #124]
   cc72c:	9400b2b5 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc730:	aa1403e1 	mov	x1, x20
   cc734:	9400a0e3 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc738:	d0000022 	adrp	x2, d2000 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE+0x3f8>
   cc73c:	9110c042 	add	x2, x2, #0x430
   cc740:	aa1703e1 	mov	x1, x23
   cc744:	aa1603e0 	mov	x0, x22
   cc748:	b9007bf9 	str	w25, [sp, #120]
   cc74c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc750:	f9004bf3 	str	x19, [sp, #144]
   cc754:	9400b9a1 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc758:	528002a2 	mov	w2, #0x15                  	// #21
   cc75c:	aa1503e1 	mov	x1, x21
   cc760:	b9007fe2 	str	w2, [sp, #124]
   cc764:	9400b2a7 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc768:	aa1403e1 	mov	x1, x20
   cc76c:	9400a0d5 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc770:	f0000022 	adrp	x2, d3000 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x598>
   cc774:	9102c042 	add	x2, x2, #0xb0
   cc778:	aa1703e1 	mov	x1, x23
   cc77c:	aa1603e0 	mov	x0, x22
   cc780:	b9007bf9 	str	w25, [sp, #120]
   cc784:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc788:	f9004bf3 	str	x19, [sp, #144]
   cc78c:	9400b993 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc790:	528002c2 	mov	w2, #0x16                  	// #22
   cc794:	aa1503e1 	mov	x1, x21
   cc798:	b9007fe2 	str	w2, [sp, #124]
   cc79c:	9400b299 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc7a0:	aa1403e1 	mov	x1, x20
   cc7a4:	9400a0c7 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc7a8:	f0000022 	adrp	x2, d3000 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x598>
   cc7ac:	91190042 	add	x2, x2, #0x640
   cc7b0:	aa1703e1 	mov	x1, x23
   cc7b4:	aa1603e0 	mov	x0, x22
   cc7b8:	b9007bf9 	str	w25, [sp, #120]
   cc7bc:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc7c0:	f9004bf3 	str	x19, [sp, #144]
   cc7c4:	9400b985 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc7c8:	528002e2 	mov	w2, #0x17                  	// #23
   cc7cc:	aa1503e1 	mov	x1, x21
   cc7d0:	b9007fe2 	str	w2, [sp, #124]
   cc7d4:	9400b28b 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc7d8:	aa1403e1 	mov	x1, x20
   cc7dc:	9400a0b9 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc7e0:	f0000022 	adrp	x2, d3000 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x598>
   cc7e4:	91276042 	add	x2, x2, #0x9d8
   cc7e8:	aa1703e1 	mov	x1, x23
   cc7ec:	aa1603e0 	mov	x0, x22
   cc7f0:	b9007bf9 	str	w25, [sp, #120]
   cc7f4:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc7f8:	f9004bf3 	str	x19, [sp, #144]
   cc7fc:	9400b977 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc800:	52800302 	mov	w2, #0x18                  	// #24
   cc804:	aa1503e1 	mov	x1, x21
   cc808:	b9007fe2 	str	w2, [sp, #124]
   cc80c:	9400b27d 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc810:	aa1403e1 	mov	x1, x20
   cc814:	9400a0ab 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc818:	d0000022 	adrp	x2, d2000 <_ZN9CmdHandle26buildResponseWithErrorCodeERKNS_9cmdInfo_tERKiNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEE+0x3f8>
   cc81c:	9129a042 	add	x2, x2, #0xa68
   cc820:	aa1703e1 	mov	x1, x23
   cc824:	aa1603e0 	mov	x0, x22
   cc828:	b9007bf9 	str	w25, [sp, #120]
   cc82c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc830:	f9004bf3 	str	x19, [sp, #144]
   cc834:	9400b969 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc838:	52800322 	mov	w2, #0x19                  	// #25
   cc83c:	aa1503e1 	mov	x1, x21
   cc840:	b9007fe2 	str	w2, [sp, #124]
   cc844:	9400b26f 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc848:	aa1403e1 	mov	x1, x20
   cc84c:	9400a09d 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc850:	f0000022 	adrp	x2, d3000 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x598>
   cc854:	91100042 	add	x2, x2, #0x400
   cc858:	aa1703e1 	mov	x1, x23
   cc85c:	aa1603e0 	mov	x0, x22
   cc860:	b9007bf9 	str	w25, [sp, #120]
   cc864:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc868:	f9004bf3 	str	x19, [sp, #144]
   cc86c:	9400b95b 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc870:	52800342 	mov	w2, #0x1a                  	// #26
   cc874:	aa1503e1 	mov	x1, x21
   cc878:	b9007fe2 	str	w2, [sp, #124]
   cc87c:	9400b261 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc880:	aa1403e1 	mov	x1, x20
   cc884:	9400a08f 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc888:	f0000022 	adrp	x2, d3000 <_ZN9CmdHandle19cmdHandle_RealSteerERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x598>
   cc88c:	9132c042 	add	x2, x2, #0xcb0
   cc890:	aa1703e1 	mov	x1, x23
   cc894:	aa1603e0 	mov	x0, x22
   cc898:	b9007bf8 	str	w24, [sp, #120]
   cc89c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc8a0:	f9004bf3 	str	x19, [sp, #144]
   cc8a4:	9400b94d 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc8a8:	aa1503e1 	mov	x1, x21
   cc8ac:	b9007ff9 	str	w25, [sp, #124]
   cc8b0:	9400b254 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc8b4:	aa1403e1 	mov	x1, x20
   cc8b8:	9400a082 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc8bc:	b0000042 	adrp	x2, d5000 <_ZZN9CmdHandle18cmdHandle_NavTasksERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tEENKUlRKS7_E_clESK_+0x808>
   cc8c0:	9120e042 	add	x2, x2, #0x838
   cc8c4:	aa1703e1 	mov	x1, x23
   cc8c8:	aa1603e0 	mov	x0, x22
   cc8cc:	b9007bf8 	str	w24, [sp, #120]
   cc8d0:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc8d4:	f9004bf3 	str	x19, [sp, #144]
   cc8d8:	9400b940 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc8dc:	52800062 	mov	w2, #0x3                   	// #3
   cc8e0:	aa1503e1 	mov	x1, x21
   cc8e4:	b9007fe2 	str	w2, [sp, #124]
   cc8e8:	9400b246 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc8ec:	aa1403e1 	mov	x1, x20
   cc8f0:	9400a074 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc8f4:	90000042 	adrp	x2, d4000 <_ZN9CmdHandle13cmdHandle_LEDERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x350>
   cc8f8:	91036042 	add	x2, x2, #0xd8
   cc8fc:	aa1703e1 	mov	x1, x23
   cc900:	aa1603e0 	mov	x0, x22
   cc904:	b9007bf8 	str	w24, [sp, #120]
   cc908:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc90c:	f9004bf3 	str	x19, [sp, #144]
   cc910:	9400b932 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc914:	52800082 	mov	w2, #0x4                   	// #4
   cc918:	aa1503e1 	mov	x1, x21
   cc91c:	b9007fe2 	str	w2, [sp, #124]
   cc920:	9400b238 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc924:	aa1403e1 	mov	x1, x20
   cc928:	9400a066 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc92c:	90000042 	adrp	x2, d4000 <_ZN9CmdHandle13cmdHandle_LEDERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x350>
   cc930:	91106042 	add	x2, x2, #0x418
   cc934:	aa1703e1 	mov	x1, x23
   cc938:	aa1603e0 	mov	x0, x22
   cc93c:	b9007bf8 	str	w24, [sp, #120]
   cc940:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc944:	f9004bf3 	str	x19, [sp, #144]
   cc948:	9400b924 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc94c:	528000a2 	mov	w2, #0x5                   	// #5
   cc950:	aa1503e1 	mov	x1, x21
   cc954:	b9007fe2 	str	w2, [sp, #124]
   cc958:	9400b22a 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc95c:	aa1403e1 	mov	x1, x20
   cc960:	9400a058 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc964:	f0000062 	adrp	x2, db000 <_ZN9CmdHandle27cmdHandle_GetLocationStatusERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x38>
   cc968:	9114e042 	add	x2, x2, #0x538
   cc96c:	aa1703e1 	mov	x1, x23
   cc970:	aa1603e0 	mov	x0, x22
   cc974:	b9007bf8 	str	w24, [sp, #120]
   cc978:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc97c:	f9004bf3 	str	x19, [sp, #144]
   cc980:	9400b916 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc984:	528000c2 	mov	w2, #0x6                   	// #6
   cc988:	aa1503e1 	mov	x1, x21
   cc98c:	b9007fe2 	str	w2, [sp, #124]
   cc990:	9400b21c 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc994:	aa1403e1 	mov	x1, x20
   cc998:	9400a04a 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc99c:	90000022 	adrp	x2, d0000 <_ZN9CmdHandle12UploadThreadEv+0x238>
   cc9a0:	9138e042 	add	x2, x2, #0xe38
   cc9a4:	aa1703e1 	mov	x1, x23
   cc9a8:	aa1603e0 	mov	x0, x22
   cc9ac:	b9007bf8 	str	w24, [sp, #120]
   cc9b0:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc9b4:	f9004bf3 	str	x19, [sp, #144]
   cc9b8:	9400b908 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc9bc:	528000e2 	mov	w2, #0x7                   	// #7
   cc9c0:	aa1503e1 	mov	x1, x21
   cc9c4:	b9007fe2 	str	w2, [sp, #124]
   cc9c8:	9400b20e 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc9cc:	aa1403e1 	mov	x1, x20
   cc9d0:	9400a03c 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cc9d4:	90000062 	adrp	x2, d8000 <_ZN9CmdHandle16cmdHandle_RebootERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0xe0>
   cc9d8:	91224042 	add	x2, x2, #0x890
   cc9dc:	aa1703e1 	mov	x1, x23
   cc9e0:	aa1603e0 	mov	x0, x22
   cc9e4:	b9007bf8 	str	w24, [sp, #120]
   cc9e8:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cc9ec:	f9004bf3 	str	x19, [sp, #144]
   cc9f0:	9400b8fa 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cc9f4:	52800102 	mov	w2, #0x8                   	// #8
   cc9f8:	aa1503e1 	mov	x1, x21
   cc9fc:	b9007fe2 	str	w2, [sp, #124]
   cca00:	9400b200 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cca04:	aa1403e1 	mov	x1, x20
   cca08:	9400a02e 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cca0c:	d0000042 	adrp	x2, d6000 <_ZN9CmdHandle19cmdHandle_SetDeviceERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x7c8>
   cca10:	9131e042 	add	x2, x2, #0xc78
   cca14:	aa1703e1 	mov	x1, x23
   cca18:	aa1603e0 	mov	x0, x22
   cca1c:	b9007bf8 	str	w24, [sp, #120]
   cca20:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cca24:	f9004bf3 	str	x19, [sp, #144]
   cca28:	9400b8ec 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cca2c:	52800122 	mov	w2, #0x9                   	// #9
   cca30:	aa1503e1 	mov	x1, x21
   cca34:	b9007fe2 	str	w2, [sp, #124]
   cca38:	9400b1f2 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cca3c:	aa1403e1 	mov	x1, x20
   cca40:	9400a020 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cca44:	b0000062 	adrp	x2, d9000 <_ZN9CmdHandle23cmdHandle_CollectTopicsERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x38>
   cca48:	91324042 	add	x2, x2, #0xc90
   cca4c:	52807d63 	mov	w3, #0x3eb                 	// #1003
   cca50:	aa1703e1 	mov	x1, x23
   cca54:	aa1603e0 	mov	x0, x22
   cca58:	f90037e2 	str	x2, [sp, #104]
   cca5c:	b9007be3 	str	w3, [sp, #120]
   cca60:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cca64:	f9004bf3 	str	x19, [sp, #144]
   cca68:	9400b8dc 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cca6c:	aa1503e1 	mov	x1, x21
   cca70:	b9007ffa 	str	w26, [sp, #124]
   cca74:	9400b1e3 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cca78:	aa1403e1 	mov	x1, x20
   cca7c:	9400a011 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cca80:	f94037e2 	ldr	x2, [sp, #104]
   cca84:	52807d60 	mov	w0, #0x3eb                 	// #1003
   cca88:	aa1703e1 	mov	x1, x23
   cca8c:	b9007be0 	str	w0, [sp, #120]
   cca90:	aa1603e0 	mov	x0, x22
   cca94:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cca98:	f9004bf3 	str	x19, [sp, #144]
   cca9c:	9400b8cf 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccaa0:	aa1503e1 	mov	x1, x21
   ccaa4:	b9007ff9 	str	w25, [sp, #124]
   ccaa8:	9400b1d6 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccaac:	aa1403e1 	mov	x1, x20
   ccab0:	9400a004 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccab4:	b0000042 	adrp	x2, d5000 <_ZZN9CmdHandle18cmdHandle_NavTasksERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tEENKUlRKS7_E_clESK_+0x808>
   ccab8:	91190042 	add	x2, x2, #0x640
   ccabc:	52807d83 	mov	w3, #0x3ec                 	// #1004
   ccac0:	aa1703e1 	mov	x1, x23
   ccac4:	aa1603e0 	mov	x0, x22
   ccac8:	b9007be3 	str	w3, [sp, #120]
   ccacc:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccad0:	f9004bf3 	str	x19, [sp, #144]
   ccad4:	9400b8c1 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccad8:	aa1503e1 	mov	x1, x21
   ccadc:	b9007ffa 	str	w26, [sp, #124]
   ccae0:	9400b1c8 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccae4:	aa1403e1 	mov	x1, x20
   ccae8:	94009ff6 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccaec:	d0000062 	adrp	x2, da000 <_ZN9CmdHandle18cmdHandle_NavTasksERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x370>
   ccaf0:	91298042 	add	x2, x2, #0xa60
   ccaf4:	52807de3 	mov	w3, #0x3ef                 	// #1007
   ccaf8:	aa1703e1 	mov	x1, x23
   ccafc:	aa1603e0 	mov	x0, x22
   ccb00:	b9007be3 	str	w3, [sp, #120]
   ccb04:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccb08:	f9004bf3 	str	x19, [sp, #144]
   ccb0c:	9400b8b3 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccb10:	aa1503e1 	mov	x1, x21
   ccb14:	b9007ffa 	str	w26, [sp, #124]
   ccb18:	9400b1ba 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccb1c:	aa1403e1 	mov	x1, x20
   ccb20:	94009fe8 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccb24:	d0000062 	adrp	x2, da000 <_ZN9CmdHandle18cmdHandle_NavTasksERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x370>
   ccb28:	913f2042 	add	x2, x2, #0xfc8
   ccb2c:	52807de3 	mov	w3, #0x3ef                 	// #1007
   ccb30:	aa1703e1 	mov	x1, x23
   ccb34:	aa1603e0 	mov	x0, x22
   ccb38:	b9007be3 	str	w3, [sp, #120]
   ccb3c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccb40:	f9004bf3 	str	x19, [sp, #144]
   ccb44:	9400b8a5 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccb48:	aa1503e1 	mov	x1, x21
   ccb4c:	b9007ff9 	str	w25, [sp, #124]
   ccb50:	9400b1ac 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccb54:	aa1403e1 	mov	x1, x20
   ccb58:	94009fda 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccb5c:	d0000042 	adrp	x2, d6000 <_ZN9CmdHandle19cmdHandle_SetDeviceERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x7c8>
   ccb60:	910a0042 	add	x2, x2, #0x280
   ccb64:	528106a3 	mov	w3, #0x835                 	// #2101
   ccb68:	aa1703e1 	mov	x1, x23
   ccb6c:	aa1603e0 	mov	x0, x22
   ccb70:	b9007be3 	str	w3, [sp, #120]
   ccb74:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccb78:	f9004bf3 	str	x19, [sp, #144]
   ccb7c:	9400b897 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccb80:	aa1503e1 	mov	x1, x21
   ccb84:	b9007ffa 	str	w26, [sp, #124]
   ccb88:	9400b19e 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccb8c:	aa1403e1 	mov	x1, x20
   ccb90:	94009fcc 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccb94:	d0000042 	adrp	x2, d6000 <_ZN9CmdHandle19cmdHandle_SetDeviceERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x7c8>
   ccb98:	91288042 	add	x2, x2, #0xa20
   ccb9c:	528106a3 	mov	w3, #0x835                 	// #2101
   ccba0:	aa1703e1 	mov	x1, x23
   ccba4:	aa1603e0 	mov	x0, x22
   ccba8:	b9007be3 	str	w3, [sp, #120]
   ccbac:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccbb0:	f9004bf3 	str	x19, [sp, #144]
   ccbb4:	9400b889 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccbb8:	aa1503e1 	mov	x1, x21
   ccbbc:	b9007ff9 	str	w25, [sp, #124]
   ccbc0:	9400b190 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccbc4:	aa1403e1 	mov	x1, x20
   ccbc8:	94009fbe 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccbcc:	90000022 	adrp	x2, d0000 <_ZN9CmdHandle12UploadThreadEv+0x238>
   ccbd0:	912e4042 	add	x2, x2, #0xb90
   ccbd4:	5280fa43 	mov	w3, #0x7d2                 	// #2002
   ccbd8:	aa1703e1 	mov	x1, x23
   ccbdc:	aa1603e0 	mov	x0, x22
   ccbe0:	b9007be3 	str	w3, [sp, #120]
   ccbe4:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccbe8:	f9004bf3 	str	x19, [sp, #144]
   ccbec:	9400b87b 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccbf0:	aa1503e1 	mov	x1, x21
   ccbf4:	b9007ffa 	str	w26, [sp, #124]
   ccbf8:	9400b182 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccbfc:	aa1403e1 	mov	x1, x20
   ccc00:	94009fb0 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccc04:	b0000082 	adrp	x2, dd000 <_ZN9CmdHandle23cmdHandle_GetOfflineNavERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5b8>
   ccc08:	911c6042 	add	x2, x2, #0x718
   ccc0c:	5280fa63 	mov	w3, #0x7d3                 	// #2003
   ccc10:	aa1703e1 	mov	x1, x23
   ccc14:	aa1603e0 	mov	x0, x22
   ccc18:	b9007be3 	str	w3, [sp, #120]
   ccc1c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccc20:	f9004bf3 	str	x19, [sp, #144]
   ccc24:	9400b86d 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccc28:	aa1503e1 	mov	x1, x21
   ccc2c:	b9007ffa 	str	w26, [sp, #124]
   ccc30:	9400b174 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccc34:	aa1403e1 	mov	x1, x20
   ccc38:	94009fa2 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccc3c:	f0000062 	adrp	x2, db000 <_ZN9CmdHandle27cmdHandle_GetLocationStatusERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x38>
   ccc40:	912f6042 	add	x2, x2, #0xbd8
   ccc44:	52817723 	mov	w3, #0xbb9                 	// #3001
   ccc48:	aa1703e1 	mov	x1, x23
   ccc4c:	aa1603e0 	mov	x0, x22
   ccc50:	b9007be3 	str	w3, [sp, #120]
   ccc54:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccc58:	f9004bf3 	str	x19, [sp, #144]
   ccc5c:	9400b85f 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccc60:	aa1503e1 	mov	x1, x21
   ccc64:	b9007fff 	str	wzr, [sp, #124]
   ccc68:	9400b166 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccc6c:	aa1403e1 	mov	x1, x20
   ccc70:	94009f94 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccc74:	d0000042 	adrp	x2, d6000 <_ZN9CmdHandle19cmdHandle_SetDeviceERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x7c8>
   ccc78:	913e4042 	add	x2, x2, #0xf90
   ccc7c:	aa1703e1 	mov	x1, x23
   ccc80:	aa1603e0 	mov	x0, x22
   ccc84:	b9007bf8 	str	w24, [sp, #120]
   ccc88:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccc8c:	f9004bf3 	str	x19, [sp, #144]
   ccc90:	9400b852 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccc94:	52800142 	mov	w2, #0xa                   	// #10
   ccc98:	aa1503e1 	mov	x1, x21
   ccc9c:	b9007fe2 	str	w2, [sp, #124]
   ccca0:	9400b158 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccca4:	aa1403e1 	mov	x1, x20
   ccca8:	94009f86 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cccac:	b0000022 	adrp	x2, d1000 <_ZN9CmdHandle24cmdHandle_GetSleepConfigERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1c8>
   cccb0:	9105a042 	add	x2, x2, #0x168
   cccb4:	aa1703e1 	mov	x1, x23
   cccb8:	aa1603e0 	mov	x0, x22
   cccbc:	b9007bf8 	str	w24, [sp, #120]
   cccc0:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cccc4:	f9004bf3 	str	x19, [sp, #144]
   cccc8:	9400b844 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccccc:	52800162 	mov	w2, #0xb                   	// #11
   cccd0:	aa1503e1 	mov	x1, x21
   cccd4:	b9007fe2 	str	w2, [sp, #124]
   cccd8:	9400b14a 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cccdc:	aa1403e1 	mov	x1, x20
   ccce0:	94009f78 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccce4:	f0ffffa2 	adrp	x2, c3000 <_Z41__static_initialization_and_destruction_0ii.constprop.0+0x9d0>
   ccce8:	91192042 	add	x2, x2, #0x648
   cccec:	aa1703e1 	mov	x1, x23
   cccf0:	aa1603e0 	mov	x0, x22
   cccf4:	b9007bf8 	str	w24, [sp, #120]
   cccf8:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cccfc:	f9004bf3 	str	x19, [sp, #144]
   ccd00:	9400b836 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccd04:	52800182 	mov	w2, #0xc                   	// #12
   ccd08:	aa1503e1 	mov	x1, x21
   ccd0c:	b9007fe2 	str	w2, [sp, #124]
   ccd10:	9400b13c 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccd14:	aa1403e1 	mov	x1, x20
   ccd18:	94009f6a 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccd1c:	90000062 	adrp	x2, d8000 <_ZN9CmdHandle16cmdHandle_RebootERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0xe0>
   ccd20:	912f8042 	add	x2, x2, #0xbe0
   ccd24:	aa1703e1 	mov	x1, x23
   ccd28:	aa1603e0 	mov	x0, x22
   ccd2c:	b9007bf8 	str	w24, [sp, #120]
   ccd30:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccd34:	f9004bf3 	str	x19, [sp, #144]
   ccd38:	9400b828 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccd3c:	528001a2 	mov	w2, #0xd                   	// #13
   ccd40:	aa1503e1 	mov	x1, x21
   ccd44:	b9007fe2 	str	w2, [sp, #124]
   ccd48:	9400b12e 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccd4c:	aa1403e1 	mov	x1, x20
   ccd50:	94009f5c 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccd54:	f0000042 	adrp	x2, d7000 <_ZN9CmdHandle32cmdHandle_SetAutoResetJointsZeroERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x70>
   ccd58:	9104c042 	add	x2, x2, #0x130
   ccd5c:	aa1703e1 	mov	x1, x23
   ccd60:	aa1603e0 	mov	x0, x22
   ccd64:	b9007bf8 	str	w24, [sp, #120]
   ccd68:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccd6c:	f9004bf3 	str	x19, [sp, #144]
   ccd70:	9400b81a 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccd74:	528001c2 	mov	w2, #0xe                   	// #14
   ccd78:	aa1503e1 	mov	x1, x21
   ccd7c:	b9007fe2 	str	w2, [sp, #124]
   ccd80:	9400b120 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccd84:	aa1403e1 	mov	x1, x20
   ccd88:	94009f4e 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccd8c:	f0000042 	adrp	x2, d7000 <_ZN9CmdHandle32cmdHandle_SetAutoResetJointsZeroERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x70>
   ccd90:	91232042 	add	x2, x2, #0x8c8
   ccd94:	aa1703e1 	mov	x1, x23
   ccd98:	aa1603e0 	mov	x0, x22
   ccd9c:	b9007bf8 	str	w24, [sp, #120]
   ccda0:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccda4:	f9004bf3 	str	x19, [sp, #144]
   ccda8:	9400b80c 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccdac:	528001e2 	mov	w2, #0xf                   	// #15
   ccdb0:	aa1503e1 	mov	x1, x21
   ccdb4:	b9007fe2 	str	w2, [sp, #124]
   ccdb8:	9400b112 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccdbc:	aa1403e1 	mov	x1, x20
   ccdc0:	94009f40 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccdc4:	f0000042 	adrp	x2, d7000 <_ZN9CmdHandle32cmdHandle_SetAutoResetJointsZeroERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x70>
   ccdc8:	912c4042 	add	x2, x2, #0xb10
   ccdcc:	aa1703e1 	mov	x1, x23
   ccdd0:	aa1603e0 	mov	x0, x22
   ccdd4:	b9007bf8 	str	w24, [sp, #120]
   ccdd8:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccddc:	f9004bf3 	str	x19, [sp, #144]
   ccde0:	9400b7fe 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccde4:	52800202 	mov	w2, #0x10                  	// #16
   ccde8:	aa1503e1 	mov	x1, x21
   ccdec:	b9007fe2 	str	w2, [sp, #124]
   ccdf0:	9400b104 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccdf4:	aa1403e1 	mov	x1, x20
   ccdf8:	94009f32 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccdfc:	f0000042 	adrp	x2, d7000 <_ZN9CmdHandle32cmdHandle_SetAutoResetJointsZeroERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x70>
   cce00:	913c8042 	add	x2, x2, #0xf20
   cce04:	aa1703e1 	mov	x1, x23
   cce08:	aa1603e0 	mov	x0, x22
   cce0c:	b9007bf8 	str	w24, [sp, #120]
   cce10:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cce14:	f9004bf3 	str	x19, [sp, #144]
   cce18:	9400b7f0 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cce1c:	52800222 	mov	w2, #0x11                  	// #17
   cce20:	aa1503e1 	mov	x1, x21
   cce24:	b9007fe2 	str	w2, [sp, #124]
   cce28:	9400b0f6 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cce2c:	aa1403e1 	mov	x1, x20
   cce30:	94009f24 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cce34:	91008380 	add	x0, x28, #0x20
   cce38:	08dffc01 	ldarb	w1, [x0]
   cce3c:	90001058 	adrp	x24, 2d4000 <_ZZN9SingletonI15ExceptionHandleE11getInstanceEvE8instance+0x350>
   cce40:	36001301 	tbz	w1, #0, cd0a0 <_ZN9CmdHandle4initEv+0xaf8>
   cce44:	9100a300 	add	x0, x24, #0x28
   cce48:	94041178 	bl	1d1428 <_ZN7Feature14isRecordEnableEv>
   cce4c:	72001c1f 	tst	w0, #0xff
   cce50:	540007a1 	b.ne	ccf44 <_ZN9CmdHandle4initEv+0x99c>  // b.any
   cce54:	91008380 	add	x0, x28, #0x20
   cce58:	08dffc01 	ldarb	w1, [x0]
   cce5c:	36001081 	tbz	w1, #0, cd06c <_ZN9CmdHandle4initEv+0xac4>
   cce60:	9100a300 	add	x0, x24, #0x28
   cce64:	9404110f 	bl	1d12a0 <_ZN7Feature12isAmapEnableEv>
   cce68:	72001c1f 	tst	w0, #0xff
   cce6c:	54000321 	b.ne	cced0 <_ZN9CmdHandle4initEv+0x928>  // b.any
   cce70:	f0000b02 	adrp	x2, 22f000 <_IO_stdin_used+0x530>
   cce74:	913ae042 	add	x2, x2, #0xeb8
   cce78:	aa0203e1 	mov	x1, x2
   cce7c:	9102a260 	add	x0, x19, #0xa8
   cce80:	9400c412 	bl	fdec8 <_ZN4toml4findIbNS_16discard_commentsESt13unordered_mapSt6vectorRA13_KcS6_JEEEDTcl3getIT_Ecl7declvalIRNS_11basic_valueIT0_T1_T2_EEEEEESD_OT3_OT4_DpOT5_>
   cce84:	39400002 	ldrb	w2, [x0]
   cce88:	f0000b01 	adrp	x1, 22f000 <_IO_stdin_used+0x530>
   cce8c:	f9407a60 	ldr	x0, [x19, #240]
   cce90:	3903e262 	strb	w2, [x19, #248]
   cce94:	913b2021 	add	x1, x1, #0xec8
   cce98:	94009ed8 	bl	f49f8 <_ZN8DrLogger4infoIJEEEvPKcDpOT_>
   cce9c:	f947eb7b 	ldr	x27, [x27, #4048]
   ccea0:	f9404fe0 	ldr	x0, [sp, #152]
   ccea4:	f9400361 	ldr	x1, [x27]
   ccea8:	eb010000 	subs	x0, x0, x1
   cceac:	d2800001 	mov	x1, #0x0                   	// #0
   cceb0:	54001141 	b.ne	cd0d8 <_ZN9CmdHandle4initEv+0xb30>  // b.any
   cceb4:	a94153f3 	ldp	x19, x20, [sp, #16]
   cceb8:	a9425bf5 	ldp	x21, x22, [sp, #32]
   ccebc:	a94363f7 	ldp	x23, x24, [sp, #48]
   ccec0:	a9446bf9 	ldp	x25, x26, [sp, #64]
   ccec4:	a94573fb 	ldp	x27, x28, [sp, #80]
   ccec8:	a8ca7bfd 	ldp	x29, x30, [sp], #160
   ccecc:	d65f03c0 	ret
   cced0:	90000082 	adrp	x2, dc000 <_ZN9CmdHandle15cmdHandle_GetSnERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x428>
   cced4:	91292042 	add	x2, x2, #0xa48
   cced8:	aa1703e1 	mov	x1, x23
   ccedc:	5284d598 	mov	w24, #0x26ac                	// #9900
   ccee0:	aa1603e0 	mov	x0, x22
   ccee4:	b9007bf8 	str	w24, [sp, #120]
   ccee8:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cceec:	f9004bf3 	str	x19, [sp, #144]
   ccef0:	9400b7ba 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccef4:	aa1503e1 	mov	x1, x21
   ccef8:	b9007fff 	str	wzr, [sp, #124]
   ccefc:	9400b0c1 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccf00:	aa1403e1 	mov	x1, x20
   ccf04:	94009eef 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccf08:	b0000082 	adrp	x2, dd000 <_ZN9CmdHandle23cmdHandle_GetOfflineNavERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x5b8>
   ccf0c:	910b0042 	add	x2, x2, #0x2c0
   ccf10:	aa1703e1 	mov	x1, x23
   ccf14:	aa1603e0 	mov	x0, x22
   ccf18:	b9007bf8 	str	w24, [sp, #120]
   ccf1c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccf20:	f9004bf3 	str	x19, [sp, #144]
   ccf24:	9400b7ad 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccf28:	52800022 	mov	w2, #0x1                   	// #1
   ccf2c:	aa1503e1 	mov	x1, x21
   ccf30:	b9007fe2 	str	w2, [sp, #124]
   ccf34:	9400b0b3 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccf38:	aa1403e1 	mov	x1, x20
   ccf3c:	94009ee1 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccf40:	17ffffcc 	b	cce70 <_ZN9CmdHandle4initEv+0x8c8>
   ccf44:	90000082 	adrp	x2, dc000 <_ZN9CmdHandle15cmdHandle_GetSnERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x428>
   ccf48:	9100a042 	add	x2, x2, #0x28
   ccf4c:	528089b9 	mov	w25, #0x44d                 	// #1101
   ccf50:	aa1703e1 	mov	x1, x23
   ccf54:	aa1603e0 	mov	x0, x22
   ccf58:	b9007bf9 	str	w25, [sp, #120]
   ccf5c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccf60:	f9004bf3 	str	x19, [sp, #144]
   ccf64:	9400b79d 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccf68:	52807d62 	mov	w2, #0x3eb                 	// #1003
   ccf6c:	aa1503e1 	mov	x1, x21
   ccf70:	b9007fe2 	str	w2, [sp, #124]
   ccf74:	9400b0a3 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccf78:	aa1403e1 	mov	x1, x20
   ccf7c:	94009ed1 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccf80:	90000082 	adrp	x2, dc000 <_ZN9CmdHandle15cmdHandle_GetSnERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x428>
   ccf84:	9114a042 	add	x2, x2, #0x528
   ccf88:	aa1703e1 	mov	x1, x23
   ccf8c:	aa1603e0 	mov	x0, x22
   ccf90:	b9007bf9 	str	w25, [sp, #120]
   ccf94:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccf98:	f9004bf3 	str	x19, [sp, #144]
   ccf9c:	9400b78f 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccfa0:	52807d82 	mov	w2, #0x3ec                 	// #1004
   ccfa4:	aa1503e1 	mov	x1, x21
   ccfa8:	b9007fe2 	str	w2, [sp, #124]
   ccfac:	9400b095 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccfb0:	aa1403e1 	mov	x1, x20
   ccfb4:	94009ec3 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccfb8:	90000062 	adrp	x2, d8000 <_ZN9CmdHandle16cmdHandle_RebootERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0xe0>
   ccfbc:	91160042 	add	x2, x2, #0x580
   ccfc0:	aa1703e1 	mov	x1, x23
   ccfc4:	aa1603e0 	mov	x0, x22
   ccfc8:	b9007bf9 	str	w25, [sp, #120]
   ccfcc:	a9087fe2 	stp	x2, xzr, [sp, #128]
   ccfd0:	f9004bf3 	str	x19, [sp, #144]
   ccfd4:	9400b781 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccfd8:	52807da2 	mov	w2, #0x3ed                 	// #1005
   ccfdc:	aa1503e1 	mov	x1, x21
   ccfe0:	b9007fe2 	str	w2, [sp, #124]
   ccfe4:	9400b087 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   ccfe8:	aa1403e1 	mov	x1, x20
   ccfec:	94009eb5 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   ccff0:	90000062 	adrp	x2, d8000 <_ZN9CmdHandle16cmdHandle_RebootERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0xe0>
   ccff4:	913f2042 	add	x2, x2, #0xfc8
   ccff8:	aa1703e1 	mov	x1, x23
   ccffc:	aa1603e0 	mov	x0, x22
   cd000:	b9007bf9 	str	w25, [sp, #120]
   cd004:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cd008:	f9004bf3 	str	x19, [sp, #144]
   cd00c:	9400b773 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cd010:	52807dc2 	mov	w2, #0x3ee                 	// #1006
   cd014:	aa1503e1 	mov	x1, x21
   cd018:	b9007fe2 	str	w2, [sp, #124]
   cd01c:	9400b079 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cd020:	aa1403e1 	mov	x1, x20
   cd024:	94009ea7 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cd028:	90000022 	adrp	x2, d1000 <_ZN9CmdHandle24cmdHandle_GetSleepConfigERN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKNS_9cmdInfo_tE+0x1c8>
   cd02c:	910e4042 	add	x2, x2, #0x390
   cd030:	aa1703e1 	mov	x1, x23
   cd034:	aa1603e0 	mov	x0, x22
   cd038:	b9007bf9 	str	w25, [sp, #120]
   cd03c:	a9087fe2 	stp	x2, xzr, [sp, #128]
   cd040:	f9004bf3 	str	x19, [sp, #144]
   cd044:	9400b765 	bl	fadd8 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt13unordered_mapIiSt8functionIFvRN9rapidjson12GenericValueINS5_4UTF8IcEENS5_19MemoryPoolAllocatorINS5_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEESt4hashIiESt8equal_toIiESaIS1_IS2_SQ_EEEESaISY_ENS_10_Select1stESU_SS_NS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cd048:	52807de2 	mov	w2, #0x3ef                 	// #1007
   cd04c:	aa1503e1 	mov	x1, x21
   cd050:	b9007fe2 	str	w2, [sp, #124]
   cd054:	9400b06b 	bl	f9200 <_ZNSt8__detail9_Map_baseIiSt4pairIKiSt8functionIFvRN9rapidjson12GenericValueINS4_4UTF8IcEENS4_19MemoryPoolAllocatorINS4_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEESaISQ_ENS_10_Select1stESt8equal_toIiESt4hashIiENS_18_Mod_range_hashingENS_20_Default_ranged_hashENS_20_Prime_rehash_policyENS_17_Hashtable_traitsILb0ELb0ELb1EEELb1EEixEOi>
   cd058:	aa1403e1 	mov	x1, x20
   cd05c:	94009e99 	bl	f4ac0 <_ZNSt8functionIFvRN9rapidjson12GenericValueINS0_4UTF8IcEENS0_19MemoryPoolAllocatorINS0_12CrtAllocatorEEEEERNSt7__cxx1112basic_stringIcSt11char_traitsIcESaIcEEERKN9CmdHandle9cmdInfo_tEEEaSISt5_BindIFMSG_FvS8_SF_SJ_EPSG_St12_PlaceholderILi1EESR_ILi2EESR_ILi3EEEEEENSt9enable_ifIXsrNSL_9_CallableINSt5decayIT_E4typeESt15__invoke_resultIRS12_JS8_SF_SJ_EEEE5valueERSL_E4typeEOS10_>
   cd060:	91008380 	add	x0, x28, #0x20
   cd064:	08dffc01 	ldarb	w1, [x0]
   cd068:	3707efc1 	tbnz	w1, #0, cce60 <_ZN9CmdHandle4initEv+0x8b8>
   cd06c:	97ff7251 	bl	a99b0 <__cxa_guard_acquire@plt>
   cd070:	34ffef80 	cbz	w0, cce60 <_ZN9CmdHandle4initEv+0x8b8>
   cd074:	9100a300 	add	x0, x24, #0x28
   cd078:	94041424 	bl	1d2108 <_ZN7FeatureC1Ev>
   cd07c:	b0001020 	adrp	x0, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   cd080:	9100a301 	add	x1, x24, #0x28
   cd084:	d0001022 	adrp	x2, 2d3000 <__data_start>
   cd088:	91002042 	add	x2, x2, #0x8
   cd08c:	f9479800 	ldr	x0, [x0, #3888]
   cd090:	97ff7650 	bl	aa9d0 <__cxa_atexit@plt>
   cd094:	91008380 	add	x0, x28, #0x20
   cd098:	97ff7402 	bl	aa0a0 <__cxa_guard_release@plt>
   cd09c:	17ffff71 	b	cce60 <_ZN9CmdHandle4initEv+0x8b8>
   cd0a0:	97ff7244 	bl	a99b0 <__cxa_guard_acquire@plt>
   cd0a4:	34ffed00 	cbz	w0, cce44 <_ZN9CmdHandle4initEv+0x89c>
   cd0a8:	9100a300 	add	x0, x24, #0x28
   cd0ac:	94041417 	bl	1d2108 <_ZN7FeatureC1Ev>
   cd0b0:	b0001020 	adrp	x0, 2d2000 <_ZNK5drdds3msg15LossStatusValue14matching_errorEv>
   cd0b4:	9100a301 	add	x1, x24, #0x28
   cd0b8:	d0001022 	adrp	x2, 2d3000 <__data_start>
   cd0bc:	91002042 	add	x2, x2, #0x8
   cd0c0:	f9479800 	ldr	x0, [x0, #3888]
   cd0c4:	97ff7643 	bl	aa9d0 <__cxa_atexit@plt>
   cd0c8:	91008380 	add	x0, x28, #0x20
   cd0cc:	97ff73f5 	bl	aa0a0 <__cxa_guard_release@plt>
   cd0d0:	17ffff5d 	b	cce44 <_ZN9CmdHandle4initEv+0x89c>
   cd0d4:	97ff7987 	bl	ab6f0 <_ZSt9terminatev@plt>
   cd0d8:	97ff794a 	bl	ab600 <__stack_chk_fail@plt>
   cd0dc:	f100043f 	cmp	x1, #0x1
   cd0e0:	54000261 	b.ne	cd12c <_ZN9CmdHandle4initEv+0xb84>  // b.any
   cd0e4:	97ff659f 	bl	a6760 <__cxa_begin_catch@plt>
   cd0e8:	f9400001 	ldr	x1, [x0]
   cd0ec:	f9407a73 	ldr	x19, [x19, #240]
   cd0f0:	f9400821 	ldr	x1, [x1, #16]
   cd0f4:	d63f0020 	blr	x1
   cd0f8:	aa0003e3 	mov	x3, x0
   cd0fc:	d0000b01 	adrp	x1, 22f000 <_IO_stdin_used+0x530>
   cd100:	aa1403e2 	mov	x2, x20
   cd104:	aa1303e0 	mov	x0, x19
   cd108:	913b8021 	add	x1, x1, #0xee0
   cd10c:	f90043e3 	str	x3, [sp, #128]
   cd110:	94009ea8 	bl	f4bb0 <_ZN8DrLogger5errorIJPKcEEEvS2_DpOT_>
   cd114:	97ff75f3 	bl	aa8e0 <__cxa_end_catch@plt>
   cd118:	17ffff61 	b	cce9c <_ZN9CmdHandle4initEv+0x8f4>
   cd11c:	aa0003f3 	mov	x19, x0
   cd120:	91008380 	add	x0, x28, #0x20
   cd124:	97ff67ef 	bl	a70e0 <__cxa_guard_abort@plt>
   cd128:	aa1303e0 	mov	x0, x19
   cd12c:	97ff6a4d 	bl	a7a60 <_Unwind_Resume@plt>
   cd130:	17fffffb 	b	cd11c <_ZN9CmdHandle4initEv+0xb74>
   cd134:	f94043e1 	ldr	x1, [sp, #128]
   cd138:	aa0003f3 	mov	x19, x0
   cd13c:	b40000a1 	cbz	x1, cd150 <_ZN9CmdHandle4initEv+0xba8>
   cd140:	f9400022 	ldr	x2, [x1]
   cd144:	aa0103e0 	mov	x0, x1
   cd148:	f9400441 	ldr	x1, [x2, #8]
   cd14c:	d63f0020 	blr	x1
   cd150:	d2800101 	mov	x1, #0x8                   	// #8
   cd154:	aa1503e0 	mov	x0, x21
   cd158:	97ff65a2 	bl	a67e0 <_ZdlPvm@plt>
   cd15c:	aa1303e0 	mov	x0, x19
   cd160:	97ff6a40 	bl	a7a60 <_Unwind_Resume@plt>
   cd164:	aa0003f3 	mov	x19, x0
   cd168:	17fffffa 	b	cd150 <_ZN9CmdHandle4initEv+0xba8>
   cd16c:	aa0003f3 	mov	x19, x0
   cd170:	97ff75dc 	bl	aa8e0 <__cxa_end_catch@plt>
   cd174:	aa1303e0 	mov	x0, x19
   cd178:	97ff6a3a 	bl	a7a60 <_Unwind_Resume@plt>
   cd17c:	d503201f 	nop
