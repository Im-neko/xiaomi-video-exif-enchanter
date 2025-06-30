#!/bin/bash

# シンプルな繰り返しバッチ処理スクリプト
# 一時ディレクトリを使わず、処理済みファイルを記録して重複を避ける

set -e

PROGRESS_FILE=".batch_progress"
PROCESSED_LIST=".processed_files"

# デフォルト値
DEFAULT_BATCH_SIZE=50
DEFAULT_LOCATION=""

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

print_progress() {
    echo -e "\033[1;36m[PROGRESS]\033[0m $1"
}

# 使用方法の表示
show_usage() {
    echo "使用方法: $0 [batch_size] [location]"
    echo ""
    echo "引数:"
    echo "  batch_size  - 1回のバッチで処理するファイル数 (デフォルト: $DEFAULT_BATCH_SIZE)"
    echo "  location    - 場所情報 (デフォルト: なし)"
    echo ""
    echo "例:"
    echo "  $0                    # デフォルト設定で実行"
    echo "  $0 30                 # 30ファイルずつ処理"
    echo "  $0 25 \"リビング\"      # 25ファイルずつ、場所付きで処理"
    echo ""
    echo "管理コマンド:"
    echo "  $0 status             # 進行状況を確認"
    echo "  $0 clean              # 進行状況をリセット"
}

# 進行状況の保存
save_progress() {
    local total_processed=$1
    local total_failed=$2
    local remaining=$3
    
    cat > $PROGRESS_FILE << EOF
TOTAL_PROCESSED=$total_processed
TOTAL_FAILED=$total_failed
REMAINING=$remaining
LAST_UPDATE=$(date)
EOF
}

# 進行状況の読み込み
load_progress() {
    if [ -f $PROGRESS_FILE ]; then
        source $PROGRESS_FILE
        return 0
    else
        return 1
    fi
}

# 進行状況の表示
show_status() {
    if load_progress; then
        echo "📊 現在の進行状況:"
        echo "  処理済み: $TOTAL_PROCESSED ファイル"
        echo "  失敗: $TOTAL_FAILED ファイル"
        echo "  残り: $REMAINING ファイル"
        echo "  最終更新: $LAST_UPDATE"
        
        # 進行率の計算
        local total_files=$((TOTAL_PROCESSED + TOTAL_FAILED + REMAINING))
        local progress_percent=0
        if [ $total_files -gt 0 ]; then
            progress_percent=$(( (TOTAL_PROCESSED + TOTAL_FAILED) * 100 / total_files ))
        fi
        echo "  進行率: ${progress_percent}%"
        
        # プログレスバーの表示
        local bar_length=50
        local filled_length=$(( progress_percent * bar_length / 100 ))
        local bar=$(printf "%${filled_length}s" | tr ' ' '█')
        local empty=$(printf "%$((bar_length - filled_length))s" | tr ' ' '░')
        echo "  [${bar}${empty}] ${progress_percent}%"
    else
        print_info "進行状況ファイルが見つかりません。"
    fi
}

# 処理済みファイルのリストを管理
mark_as_processed() {
    local file=$1
    echo "$file" >> $PROCESSED_LIST
}

is_already_processed() {
    local file=$1
    if [ -f $PROCESSED_LIST ]; then
        grep -Fxq "$file" $PROCESSED_LIST
    else
        return 1
    fi
}

# 単一ファイル処理
process_single_file() {
    local input_file=$1
    local location=$2
    
    local filename=$(basename "$input_file")
    local output_file="output/${filename%.*}_enhanced.mp4"
    
    print_progress "処理中: $filename"
    
    # Docker コマンドを構築
    local cmd_args=(
        "$input_file"
        "--output" "$output_file"
        "--debug"
    )
    
    if [ -n "$location" ]; then
        cmd_args+=("--location" "$location")
    fi
    
    # 単一ファイル処理を実行
    if docker run --rm \
        -v "$(pwd)/input:/app/input:ro" \
        -v "$(pwd)/output:/app/output:rw" \
        xiaomi-exif-enhancer "${cmd_args[@]}"; then
        
        print_success "✅ 処理完了: $filename"
        return 0
    else
        print_error "❌ 処理失敗: $filename"
        return 1
    fi
}

# メイン処理関数
run_simple_batch() {
    local batch_size=${1:-$DEFAULT_BATCH_SIZE}
    local location=${2:-$DEFAULT_LOCATION}
    
    print_info "シンプルバッチ処理を開始します"
    print_info "バッチサイズ: $batch_size ファイル"
    print_info "場所: ${location:-\"未指定\"}"
    
    # 全ファイルを取得
    local all_files=($(find input -name "*.mp4" -o -name "*.MP4" | sort))
    local total_files=${#all_files[@]}
    
    if [ $total_files -eq 0 ]; then
        print_error "処理するファイルが見つかりません"
        return 1
    fi
    
    print_info "総ファイル数: $total_files"
    
    # 出力ディレクトリを作成
    mkdir -p output
    
    local processed=0
    local failed=0
    local batch_count=0
    
    for file in "${all_files[@]}"; do
        # 処理済みチェック
        if is_already_processed "$file"; then
            print_info "⏭️ スキップ (処理済み): $(basename "$file")"
            ((processed++))
            continue
        fi
        
        # バッチサイズに達したら進行状況を保存
        if [ $((batch_count % batch_size)) -eq 0 ] && [ $batch_count -gt 0 ]; then
            local remaining=$((total_files - processed - failed))
            save_progress $processed $failed $remaining
            print_info "🔄 進行状況を保存しました (処理済み: $processed, 失敗: $failed, 残り: $remaining)"
            
            # 短時間の休憩
            print_info "⏱️ 10秒待機中..."
            sleep 10
        fi
        
        # ファイル処理
        if process_single_file "$file" "$location"; then
            mark_as_processed "$file"
            ((processed++))
        else
            mark_as_processed "$file"  # 失敗したファイルも記録して重複を防ぐ
            ((failed++))
        fi
        
        ((batch_count++))
        
        # 進行状況表示
        local remaining=$((total_files - processed - failed))
        echo "📈 進行状況: 処理済み $processed, 失敗 $failed, 残り $remaining"
    done
    
    # 最終結果
    save_progress $processed $failed 0
    
    print_success "🏁 バッチ処理が完了しました！"
    print_info "総処理ファイル数: $processed"
    print_info "失敗ファイル数: $failed"
    
    show_status
}

# メイン処理
case "${1:-}" in
    "status")
        show_status
        ;;
    "clean")
        print_warning "進行状況をリセットします..."
        rm -f $PROGRESS_FILE $PROCESSED_LIST
        print_success "リセットが完了しました"
        ;;
    "help"|"--help"|"-h")
        show_usage
        ;;
    "")
        # デフォルト実行
        run_simple_batch $DEFAULT_BATCH_SIZE "$DEFAULT_LOCATION"
        ;;
    *)
        # 引数が数字の場合はバッチサイズとして処理
        if [[ $1 =~ ^[0-9]+$ ]]; then
            run_simple_batch "$1" "$2"
        else
            print_error "不明なコマンド: $1"
            show_usage
            exit 1
        fi
        ;;
esac