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
      ('bnk_mngt_pcbg', 'bnkMngtPcbg', '채권은행'),
      ('bnk_mngt_pcsp', 'bnkMngtPcsp', '채권은행'),

      -- 소송 (1)
      ('lwst_lg', 'lwstLg', '소송'),

      -- 해외상장 (4)
      ('ov_lst_decsn', 'ovLstDecsn', '해외상장'),
      ('ov_dlst_decsn', 'ovDlstDecsn', '해외상장'),
      ('ov_lst', 'ovLst', '해외상장'),
      ('ov_dlst', 'ovDlst', '해외상장'),

      -- 사채발행 (4)
      ('cvbd_is_decsn', 'cvbdIsDecsn', '사채발행'),
      ('bdwt_is_decsn', 'bdwtIsDecsn', '사채발행'),
      ('exbd_is_decsn', 'exbdIsDecsn', '사채발행'),
      ('wd_cocobd_is_decsn', 'wdCocobdIsDecsn', '사채발행'),

      -- 자기주식 (4)
      ('tsstk_aq_decsn', 'tsstkAqDecsn', '자기주식'),
      ('tsstk_dp_decsn', 'tsstkDpDecsn', '자기주식'),
      ('tsstk_aq_trctr_cns_decsn', 'tsstkAqTrctrCnsDecsn', '자기주식'),
      ('tsstk_aq_trctr_cc_decsn', 'tsstkAqTrctrCcDecsn', '자기주식'),

      -- 영업양수도 (2)
      ('bsn_inh_decsn', 'bsnInhDecsn', '영업양수도'),
      ('bsn_trf_decsn', 'bsnTrfDecsn', '영업양수도'),

      -- 자산양수도 (2)
      ('tgast_inh_decsn', 'tgastInhDecsn', '자산양수도'),
      ('tgast_trf_decsn', 'tgastTrfDecsn', '자산양수도'),

      -- 타법인주식 (2)
      ('otcpr_stk_invscr_inh_decsn', 'otcprStkInvscrInhDecsn', '타법인주식'),
      ('otcpr_stk_invscr_trf_decsn', 'otcprStkInvscrTrfDecsn', '타법인주식'),

      -- 사채권양수도 (2)
      ('stkrtbd_inh_decsn', 'stkrtbdInhDecsn', '사채권양수도'),
      ('stkrtbd_trf_decsn', 'stkrtbdTrfDecsn', '사채권양수도'),

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


