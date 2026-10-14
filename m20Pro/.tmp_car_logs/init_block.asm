
/opt/robot/share/basic_server/bin/basic_server:     file format elf64-littleaarch64


Disassembly of section .text:

00000000000ccb80 <_ZN9CmdHandle4initEv+0x5d8>:
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
