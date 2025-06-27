#!/bin/bash

# 繰り返しバッチ処理のデモンストレーション

echo "🎬 繰り返しバッチ処理デモ"
echo "========================"

echo ""
echo "📊 現在の状況:"
echo "  入力ファイル数: $(ls input/*.mp4 | wc -l)"
echo "  処理済みファイル数: $(find output -name "*_enhanced.mp4" 2>/dev/null | wc -l || echo 0)"
echo "  失敗ファイル数: $(find output/failed -name "*.mp4" 2>/dev/null | wc -l || echo 0)"

echo ""
echo "🔧 利用可能なコマンド:"
echo ""
echo "1. 基本的な繰り返し処理:"
echo "   ./run_batch.sh repeat"
echo "   ./run_batch_repeat.sh"
echo ""
echo "2. カスタム設定:"
echo "   ./run_batch_repeat.sh 20              # 20ファイルずつ"
echo "   ./run_batch_repeat.sh 30 'リビング'    # 場所付き"
echo "   ./run_batch_repeat.sh 25 '寝室' 10     # 最大10回繰り返し"
echo ""
echo "3. 管理コマンド:"
echo "   ./run_batch_repeat.sh status          # 進行状況確認"
echo "   ./run_batch_repeat.sh resume          # 再開"
echo "   ./run_batch_repeat.sh reset           # リセット"
echo "   ./run_batch_repeat.sh clean           # クリーンアップ"
echo ""
echo "4. Docker Compose版:"
echo "   docker-compose -f docker-compose.safe.yml --profile small-batch up"
echo "   docker-compose -f docker-compose.safe.yml --profile medium-batch up"
echo ""

echo "💡 推奨実行例（2370ファイル用）:"
echo ""
echo "# 段階的アプローチ"
echo "1️⃣ ./run_batch_repeat.sh 10 'リビング' 5    # まず50ファイルでテスト"
echo "2️⃣ ./run_batch_repeat.sh status               # 進行確認"
echo "3️⃣ ./run_batch_repeat.sh 30 'リビング'        # 問題なければ30ファイルずつ"
echo "4️⃣ ./run_batch_repeat.sh status               # 定期的に確認"
echo ""
echo "# 一括処理"
echo "🚀 nohup ./run_batch_repeat.sh 50 'リビング' 50 > batch.log 2>&1 &"
echo ""

# 実際の状況確認
if [ -f ".batch_progress" ]; then
    echo "📈 現在の進行状況:"
    ./run_batch_repeat.sh status
else
    echo "📋 進行状況: 未開始"
fi

echo ""
echo "🔍 ファイル詳細:"
echo "  入力ディレクトリ: $(du -sh input 2>/dev/null | cut -f1 || echo 'N/A')"
echo "  出力ディレクトリ: $(du -sh output 2>/dev/null | cut -f1 || echo 'N/A')"

echo ""
echo "⚡ テスト実行（デモ用）:"
echo "   ./run_batch_repeat.sh 1 'デモ' 1     # 1ファイルのみテスト"