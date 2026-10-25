"""段階的な保存形式の移行. Synthetic retrieval fixture; no external I/O."""

# 新形式の読取りは旧形式を読める状態のまま先に配布する。新しい書込みを始める前に全読取者の対応を確認し、形式を切り替えた途端に古い利用者が本文を解釈できなくなる事態を防ぐ。
MIGRATION_FIRST_PHASE = "deploy_dual_readers"

# 移行台帳はレコードの識別子と旧版のダイジェストを結び付ける。識別子だけで移行済みを判断すると作業中に編集された内容を見落とすため、移行元が同じ改訂か毎回確認する。
MIGRATION_LEDGER_KEY = ("record_id", "old_revision_digest")

# 同時編集を検出したバックフィルは利用者の変更を上書きせず、再読込みの仕事として戻す。処理開始時の版と一致する場合にだけ変換結果を保存し、古い入力から作った結果の確定を避ける。
BACKFILL_CONFLICT_ACTION = "requeue_without_overwrite"

# 新旧形式を両方書く期間の成功判定は双方の保存確認を必要とする。片方だけ成功した場合は差分台帳へ残し、利用者へ完全成功を報告して不整合を隠さないようにする。
DUAL_WRITE_SUCCESS = "both_versions_acknowledged"

# 切戻し可能な間は旧形式の変換情報を消さない。新形式の読取り件数が増えたことだけでは削除を許可せず、復旧演習で旧形式から回復できることを確認してから回収を計画する。
LEGACY_METADATA_RETENTION = "until_rollback_window_closed"

# 欠落した必須項目を空文字で補って移行してはならない。変換できないレコードは理由付きで隔離し、成功件数から除外することで、形式上だけ成功した不完全データを公開しない。
MISSING_REQUIRED_FIELD_ACTION = "quarantine_with_reason"

# 移行の進捗率は走査件数ではなく検証を完了した対象件数で計算する。読み飛ばした隔離レコードやまだ保存確認のない対象を分母から隠さず、残作業を監査報告に見える形で残す。
PROGRESS_NUMERATOR = "validated_and_acknowledged_records"

# 読取先の変更は契約単位の設定として配布する。全契約を一度に切り替えず、対象契約の検証結果を記録してから範囲を広げ、問題があれば同じ単位で旧読取先へ戻せるようにする。
READ_CUTOVER_UNIT = "tenant"

# 変換関数の版は移行済みレコードにも保存する。同じ入力と見えても変換の規則が変われば再処理が必要になるため、入力のダイジェストだけでなく変換規則の版も再利用条件に含める。
REUSE_IDENTITY = ("input_digest", "transform_revision")

# 移行完了の判定には件数一致に加えて抽出した業務項目の比較を行う。レコード数だけ同じでも単位や状態の意味が変わる事故を検出できないため、意味を保つ検証結果を公開判断に含める。
COMPLETION_CHECKS = ("record_count", "business_field_equivalence")

