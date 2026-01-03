-- DART 36 Major Report Type Collection - Local PostgreSQL schema
-- ------------------------------------------------------------
-- Updated Strategy (2026-01-03):
-- - Collect 36 structured major-report endpoints (endpoint.json)
-- - Store raw structured payload as JSONB (no LLM parsing at this stage)
-- - Create one table per endpoint: dart_{snake_case(endpoint)}
--
-- Notes:
-- - Deduplication key: rcept_no (PRIMARY KEY)
-- - Common query patterns supported via indexes on (corp_code, rcept_dt), (stock_code, rcept_dt), rcept_dt

DO $$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT * FROM (VALUES
      -- 기업상태 (5)
      ('ast_inhtrf_etc_ptbk_opt', 'astInhtrfEtcPtbkOpt', '기업상태'),
      ('df_ocr', 'dfOcr', '기업상태'),
      ('bsn_sp', 'bsnSp', '기업상태'),
      ('ctrcvs_bgrq', 'ctrcvsBgrq', '기업상태'),
      ('ds_rs_ocr', 'dsRsOcr', '기업상태'),

      -- 증자감자 (4)
      ('piic_decsn', 'piicDecsn', '증자감자'),
      ('fric_decsn', 'fricDecsn', '증자감자'),
      ('pifric_decsn', 'pifricDecsn', '증자감자'),
      ('cr_decsn', 'crDecsn', '증자감자'),

      -- 채권은행 (2)
      ('ex_bnk_mng_pcbg', 'exBnkMngPcbg', '채권은행'),
      ('ex_bnk_mng_pcsp', 'exBnkMngPcsp', '채권은행'),

      -- 소송 (1)
      ('lwst_etc_prps', 'lwstEtcPrps', '소송'),

      -- 해외상장 (4)
      ('ovscs_mkt_lst_decsn', 'ovscsMktLstDecsn', '해외상장'),
      ('ovscs_mkt_dlst_decsn', 'ovscsMktDlstDecsn', '해외상장'),
      ('ovscs_mkt_lst', 'ovscsMktLst', '해외상장'),
      ('ovscs_mkt_dlst', 'ovscsMktDlst', '해외상장'),

      -- 사채발행 (4)
      ('cvbd_is_decsn', 'cvbdIsDecsn', '사채발행'),
      ('bdwt_is_decsn', 'bdwtIsDecsn', '사채발행'),
      ('exbd_is_decsn', 'exbdIsDecsn', '사채발행'),
      ('woccs_is_decsn', 'woccsIsDecsn', '사채발행'),

      -- 자기주식 (4)
      ('tsstk_aq_decsn', 'tsstkAqDecsn', '자기주식'),
      ('tsstk_dp_decsn', 'tsstkDpDecsn', '자기주식'),
      ('tsstk_aq_trc_ctr_decsn', 'tsstkAqTrcCtrDecsn', '자기주식'),
      ('tsstk_aq_trc_ctr_cc_decsn', 'tsstkAqTrcCtrCcDecsn', '자기주식'),

      -- 영업양수도 (2)
      ('bsn_inh_decsn', 'bsnInhDecsn', '영업양수도'),
      ('bsn_trf_decsn', 'bsnTrfDecsn', '영업양수도'),

      -- 자산양수도 (2)
      ('tg_ast_inh_decsn', 'tgAstInhDecsn', '자산양수도'),
      ('tg_ast_trf_decsn', 'tgAstTrfDecsn', '자산양수도'),

      -- 타법인주식 (2)
      ('otcpr_stk_inh_decsn', 'otcprStkInhDecsn', '타법인주식'),
      ('otcpr_stk_trf_decsn', 'otcprStkTrfDecsn', '타법인주식'),

      -- 사채권양수도 (2)
      ('stk_rtbd_inh_decsn', 'stkRtbdInhDecsn', '사채권양수도'),
      ('stk_rtbd_trf_decsn', 'stkRtbdTrfDecsn', '사채권양수도'),

      -- 합병분할 (4)
      ('cmp_mg_decsn', 'cmpMgDecsn', '합병분할'),
      ('cmp_dv_decsn', 'cmpDvDecsn', '합병분할'),
      ('cmp_dvmg_decsn', 'cmpDvmgDecsn', '합병분할'),
      ('stk_extr_decsn', 'stkExtrDecsn', '합병분할')
    ) AS t(table_suffix, endpoint, category)
  LOOP
    -- Create table
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS dart_%I (
         rcept_no VARCHAR(20) PRIMARY KEY,
         corp_code VARCHAR(8) NOT NULL,
         stock_code VARCHAR(6),
         corp_name VARCHAR(100),
         rcept_dt DATE NOT NULL,
         report_type VARCHAR(64) DEFAULT %L,
         category VARCHAR(64) DEFAULT %L,
         collected_at TIMESTAMPTZ DEFAULT NOW(),
         payload JSONB NOT NULL,
         created_at TIMESTAMPTZ DEFAULT NOW()
       );',
      r.table_suffix,
      r.endpoint,
      r.category
    );

    -- Indexes
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS %I ON dart_%I (corp_code, rcept_dt DESC);',
      'idx_dart_' || r.table_suffix || '_corp_dt',
      r.table_suffix
    );
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS %I ON dart_%I (stock_code, rcept_dt DESC);',
      'idx_dart_' || r.table_suffix || '_stock_dt',
      r.table_suffix
    );
    EXECUTE format(
      'CREATE INDEX IF NOT EXISTS %I ON dart_%I (rcept_dt DESC);',
      'idx_dart_' || r.table_suffix || '_dt',
      r.table_suffix
    );
  END LOOP;
END $$;


