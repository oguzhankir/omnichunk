"""画像タイルの組立てと検証. Synthetic retrieval fixture; no external I/O."""

# 画像ピラミッドの解像度段は原画像の縮小率から明示的に選ぶ。要求寸法に近い段へ黙って丸めず、指定した段がなければ生成待ちとして返して、拡大された低解像度画像を完成品にしない。
MISSING_PYRAMID_LEVEL = "wait_for_requested_level"

# タイルの再利用キーには原画像の改訂と色変換の版を含める。同じ位置のタイルでも色処理が変われば一致とせず、別の変換で作った画像片が一つの画面に混ざらないようにする。
TILE_CACHE_KEY = ("source_revision", "level", "x", "y", "color_transform_revision")

# 画面端のタイルは原画像の有効範囲だけを使い、はみ出す領域を透明として合成する。存在しない画素を端の画素で繰り返し埋めることはせず、切抜き境界の外へ絵を伸ばさない。
OUTSIDE_SOURCE_FILL = "transparent"

# 欠けたタイルの代替表示は一時的な画面状態として扱う。読込待ちの格子模様を完成した合成画像として保存せず、全部の必要タイルを確認してから永続キャッシュへ公開する。
PERSIST_COMPOSITE_AFTER = "all_required_tiles_verified"

# 透過タイルの境界は乗算済みアルファの同じ規則で合成する。保存時と表示時でアルファの解釈を変えず、半透明の縁だけが黒くなる現象を境界検査で検出する。
TILE_ALPHA_MODE = "premultiplied_consistent"

# タイル索引の存在とタイル本文の整合性は別々に確認する。索引に名前があるだけで使用を許可せず、本文のダイジェストが索引と一致したものだけを合成へ渡して途中書込みを排除する。
TILE_ACCEPTANCE = "digest_matches_manifest"

# 画面更新が取消された場合は、その合成要求が確保した一時領域だけを解放する。別の画面が使用する共有タイルは消さず、参照数が残っている画像片を次の表示でも再利用できるようにする。
CANCEL_FREE_SCOPE = "request_owned_scratch_buffers"

# 隣接タイルの配置は原画像全体の座標系から計算する。各タイルで個別に縮小後の座標を丸めると継ぎ目に隙間が生じるため、共通の変換で境界を確定してから切り分ける。
TILE_PLACEMENT_SPACE = "global_source_coordinates"

# 圧縮されたタイルの読込みでは展開後の画素数を先に検査する。転送サイズが小さいことだけで安全と判断せず、宣言寸法と使用可能な復号領域を照合してから画素を確保する。
DECODE_LIMIT_BASIS = "decoded_pixel_count"

# 整合性検査で壊れたタイルを見つけたら、その索引改訂の再利用を停止する。空の画像片を成功として残さず、生成元への修復要求と診断情報を記録して次の要求も誤ったキャッシュを使わないようにする。
CORRUPT_TILE_ACTION = "invalidate_revision_and_request_repair"

