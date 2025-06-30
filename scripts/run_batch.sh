#!/bin/bash

# Xiaomi Video EXIF Enhancer - Docker Compose バッチ処理スクリプト
# 使用方法: ./run_batch.sh [small|medium|large|single|location|continue]

set -e

COMPOSE_FILE="docker-compose.safe.yml"

# 色付き出力用の関数
print_info() {
    echo -e "\033[1;34m[INFO]\033[0m $1"
}

print_success() {
    echo -e "\033[1;32m[SUCCESS]\033[0m $1"
}

print_warning() {
    echo -e "\033[1;33m[WARNING]\033[0m $1"
}

print_error() {
    echo -e "\033[1;31m[ERROR]\033[0m $1"
}

# 引数チェック
if [ $# -eq 0 ]; then
    print_info "使用方法: $0 [command] [options]"
    echo ""
    echo "利用可能なコマンド:"
    echo "  small     - 小バッチ処理 (20ファイル)"
    echo "  medium    - 中バッチ処理 (50ファイル)"
    echo "  large     - 大バッチ処理 (100ファイル)"
    echo "  single    - 単一ファイル処理"
    echo "  location  - 場所付きバッチ処理 (30ファイル)"
    echo "  continue  - 継続処理 (25ファイル)"
    echo "  repeat    - 繰り返しバッチ処理 (推奨: 大量ファイル用)"
    echo "  build     - Dockerイメージをビルド"
    echo "  clean     - 停止中のコンテナを削除"
    echo ""
    echo "例:"
    echo "  $0 small          # 小バッチで処理"
    echo "  $0 medium         # 中バッチで処理"  
    echo "  $0 location リビング # 場所を指定してバッチ処理"
    echo "  $0 repeat         # 自動繰り返し処理 (大量ファイル推奨)"
    exit 1
fi

COMMAND=$1
LOCATION=${2:-""}

# ディレクトリの確認
print_info "ディレクトリの確認中..."
if [ ! -d "input" ]; then
    print_warning "inputディレクトリが存在しません。作成します。"
    mkdir -p input
fi

if [ ! -d "output" ]; then
    print_warning "outputディレクトリが存在しません。作成します。"
    mkdir -p output
fi

# ファイル数の確認
VIDEO_COUNT=$(find input -name "*.mp4" -o -name "*.MP4" | wc -l)
print_info "inputディレクトリ内の動画ファイル数: $VIDEO_COUNT"

if [ "$VIDEO_COUNT" -eq 0 ]; then
    print_error "処理する動画ファイルが見つかりません。"
    print_info "inputディレクトリに動画ファイル（.mp4）を配置してください。"
    exit 1
fi

# コマンド実行
case $COMMAND in
    "build")
        print_info "Dockerイメージをビルド中..."
        docker-compose -f $COMPOSE_FILE build
        print_success "Dockerイメージのビルドが完了しました。"
        ;;
    
    "small")
        print_info "小バッチ処理を開始します (20ファイル)..."
        print_warning "処理時間目安: 約 $(( (VIDEO_COUNT < 20 ? VIDEO_COUNT : 20) * 2 )) 分"
        docker-compose -f $COMPOSE_FILE --profile small-batch up --remove-orphans
        ;;
    
    "medium")
        print_info "中バッチ処理を開始します (50ファイル)..."
        print_warning "処理時間目安: 約 $(( (VIDEO_COUNT < 50 ? VIDEO_COUNT : 50) * 2 )) 分"
        docker-compose -f $COMPOSE_FILE --profile medium-batch up --remove-orphans
        ;;
    
    "large")
        print_warning "大バッチ処理を開始します (100ファイル)..."
        print_warning "処理時間目安: 約 $(( (VIDEO_COUNT < 100 ? VIDEO_COUNT : 100) * 2 )) 分"
        print_warning "長時間の処理になります。Ctrl+Cで中断できます。"
        read -p "続行しますか？ (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose -f $COMPOSE_FILE --profile large-batch up --remove-orphans
        else
            print_info "処理をキャンセルしました。"
            exit 0
        fi
        ;;
    
    "single")
        print_info "単一ファイル処理を開始します..."
        docker-compose -f $COMPOSE_FILE --profile single up --remove-orphans
        ;;
    
    "location")
        if [ -z "$LOCATION" ]; then
            read -p "場所を入力してください (例: リビング): " LOCATION
        fi
        print_info "場所付きバッチ処理を開始します (30ファイル, 場所: $LOCATION)..."
        
        # 一時的なdocker-compose.ymlを作成して場所を設定
        sed "s/リビング/$LOCATION/g" $COMPOSE_FILE > docker-compose.tmp.yml
        docker-compose -f docker-compose.tmp.yml --profile batch-location up --remove-orphans
        rm -f docker-compose.tmp.yml
        ;;
    
    "continue")
        print_info "継続処理を開始します (25ファイル)..."
        print_info "エラーファイルは自動的にスキップされます。"
        docker-compose -f $COMPOSE_FILE --profile continue up --remove-orphans
        ;;
    
    "repeat")
        print_info "繰り返しバッチ処理を開始します..."
        print_warning "大量ファイル処理用の自動実行モードです"
        print_info "詳細オプションが必要な場合は ./run_batch_repeat.sh を使用してください"
        
        # 繰り返し処理スクリプトを実行
        if [ -f "./run_batch_repeat.sh" ]; then
            ./run_batch_repeat.sh
        else
            print_error "run_batch_repeat.sh が見つかりません"
            exit 1
        fi
        ;;
    
    "clean")
        print_info "停止中のコンテナを削除中..."
        docker-compose -f $COMPOSE_FILE down --remove-orphans
        docker system prune -f
        print_success "クリーンアップが完了しました。"
        ;;
    
    *)
        print_error "不明なコマンド: $COMMAND"
        print_info "利用可能なコマンド: small, medium, large, single, location, continue, repeat, build, clean"
        exit 1
        ;;
esac

# 処理結果の確認
if [ -d "output" ] && [ "$COMMAND" != "build" ] && [ "$COMMAND" != "clean" ]; then
    PROCESSED_COUNT=$(find output -name "*_enhanced.mp4" | wc -l)
    FAILED_COUNT=$(find output/failed -name "*.mp4" 2>/dev/null | wc -l || echo 0)
    
    echo ""
    print_success "処理が完了しました！"
    print_info "成功: $PROCESSED_COUNT ファイル"
    if [ "$FAILED_COUNT" -gt 0 ]; then
        print_warning "失敗: $FAILED_COUNT ファイル (output/failedフォルダを確認)"
    fi
fi