#!/bin/bash

# Xiaomi Video EXIF Enhancer - 繰り返しバッチ処理スクリプト
# 使用方法: ./run_batch_repeat.sh [batch_size] [location] [max_iterations]

set -e

COMPOSE_FILE="docker-compose.safe.yml"
PROGRESS_FILE=".batch_progress"
PROCESSED_LIST=".processed_files"

# デフォルト値
DEFAULT_BATCH_SIZE=50
DEFAULT_MAX_ITERATIONS=100
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
    echo "使用方法: $0 [batch_size] [location] [max_iterations]"
    echo ""
    echo "引数:"
    echo "  batch_size      - 1回のバッチで処理するファイル数 (デフォルト: $DEFAULT_BATCH_SIZE)"
    echo "  location        - 場所情報 (デフォルト: なし)"
    echo "  max_iterations  - 最大繰り返し回数 (デフォルト: $DEFAULT_MAX_ITERATIONS)"
    echo ""
    echo "例:"
    echo "  $0                    # デフォルト設定で実行"
    echo "  $0 30                 # 30ファイルずつ処理"
    echo "  $0 25 \"リビング\"      # 25ファイルずつ、場所付きで処理"
    echo "  $0 40 \"寝室\" 50       # 40ファイルずつ、最大50回繰り返し"
    echo ""
    echo "管理コマンド:"
    echo "  $0 status             # 進行状況を確認"
    echo "  $0 resume             # 中断された処理を再開"
    echo "  $0 reset              # 進行状況をリセット"
    echo "  $0 clean              # 一時ファイルをクリーンアップ"
}

# 進行状況の保存
save_progress() {
    local iteration=$1
    local total_processed=$2
    local total_failed=$3
    local remaining=$4
    
    cat > $PROGRESS_FILE << EOF
ITERATION=$iteration
TOTAL_PROCESSED=$total_processed
TOTAL_FAILED=$total_failed
REMAINING=$remaining
LAST_UPDATE=$(date)
BATCH_SIZE=$BATCH_SIZE
LOCATION=$LOCATION
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
        echo "  反復回数: $ITERATION"
        echo "  処理済み: $TOTAL_PROCESSED ファイル"
        echo "  失敗: $TOTAL_FAILED ファイル"
        echo "  残り: $REMAINING ファイル"
        echo "  バッチサイズ: $BATCH_SIZE"
        echo "  場所: ${LOCATION:-\"未指定\"}"
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
        print_info "進行状況ファイルが見つかりません。初回実行または進行状況がリセットされています。"
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

# 未処理ファイルのリストを取得
get_unprocessed_files() {
    local all_files=($(find input -name "*.mp4" -o -name "*.MP4" | sort))
    local unprocessed_files=()
    
    for file in "${all_files[@]}"; do
        if ! is_already_processed "$file"; then
            unprocessed_files+=("$file")
        fi
    done
    
    printf '%s\n' "${unprocessed_files[@]}"
}

# 一時的な入力ディレクトリを作成
create_batch_input() {
    local batch_num=$1
    local files_array=("${@:2}")
    local batch_dir="input_batch_$batch_num"
    
    # 前の一時ディレクトリを削除
    rm -rf input_batch_*
    
    # 新しい一時ディレクトリを作成
    mkdir -p "$batch_dir"
    
    # ファイルをシンボリックリンクでコピー
    for file in "${files_array[@]}"; do
        if [ -f "$file" ]; then
            local filename=$(basename "$file")
            ln -sf "$(realpath "$file")" "$batch_dir/$filename"
        else
            print_warning "ファイルが見つかりません: $file"
        fi
    done
    
    echo "$batch_dir"
}

# バッチ処理の実行
run_single_batch() {
    local iteration=$1
    local batch_input_dir=$2
    local files_count=$3
    
    print_progress "バッチ $iteration を実行中... ($files_count ファイル)"
    
    # Docker Composeコマンドを構築
    local cmd_args=(
        "--batch" "/app/$batch_input_dir"
        "--batch-size" "$BATCH_SIZE"
        "--disable-parallel"
        "--debug"
    )
    
    if [ -n "$LOCATION" ]; then
        cmd_args+=("--location" "$LOCATION")
    fi
    
    # デバッグ: 実行コマンドを表示
    print_info "実行コマンド: docker run --rm -v $(pwd)/input:/app/input:ro -v $(pwd)/output:/app/output:rw -v $(pwd)/$batch_input_dir:/app/$batch_input_dir:ro xiaomi-exif-enhancer ${cmd_args[*]}"
    
    # バッチ処理を実行（直接Dockerコマンドを使用）
    if docker run --rm \
        -v "$(pwd)/input:/app/input:ro" \
        -v "$(pwd)/output:/app/output:rw" \
        -v "$(pwd)/$batch_input_dir:/app/$batch_input_dir:ro" \
        xiaomi-exif-enhancer "${cmd_args[@]}"; then
        
        print_success "バッチ $iteration が完了しました"
        return 0
    else
        print_error "バッチ $iteration でエラーが発生しました"
        return 1
    fi
}

# メイン処理関数
run_repeat_batch() {
    local batch_size=${1:-$DEFAULT_BATCH_SIZE}
    local location=${2:-$DEFAULT_LOCATION}
    local max_iterations=${3:-$DEFAULT_MAX_ITERATIONS}
    
    BATCH_SIZE=$batch_size
    LOCATION=$location
    
    print_info "繰り返しバッチ処理を開始します"
    print_info "バッチサイズ: $BATCH_SIZE ファイル"
    print_info "場所: ${LOCATION:-\"未指定\"}"
    print_info "最大繰り返し回数: $max_iterations"
    
    # 初期状態の設定
    local iteration=1
    local total_processed=0
    local total_failed=0
    
    # 進行状況が存在する場合は継続
    if load_progress; then
        iteration=$((ITERATION + 1))
        total_processed=$TOTAL_PROCESSED
        total_failed=$TOTAL_FAILED
        print_info "前回の進行状況から継続します (反復 $iteration から)"
    fi
    
    while [ $iteration -le $max_iterations ]; do
        print_info "=== 反復 $iteration/$max_iterations ==="
        
        # 未処理ファイルを取得
        mapfile -t unprocessed_files < <(get_unprocessed_files)
        local remaining_count=${#unprocessed_files[@]}
        
        if [ $remaining_count -eq 0 ]; then
            print_success "🎉 すべてのファイルの処理が完了しました！"
            break
        fi
        
        print_info "残り $remaining_count ファイル"
        
        # バッチ用のファイルを選択
        local batch_files=()
        local count=0
        for file in "${unprocessed_files[@]}"; do
            if [ $count -ge $BATCH_SIZE ]; then
                break
            fi
            batch_files+=("$file")
            ((count++))
        done
        
        # 一時的な入力ディレクトリを作成
        local batch_input_dir=$(create_batch_input $iteration "${batch_files[@]}")
        
        # 進行状況を保存
        save_progress $iteration $total_processed $total_failed $remaining_count
        
        # バッチ処理を実行
        if run_single_batch $iteration $batch_input_dir ${#batch_files[@]}; then
            # 成功したファイルをマーク
            for file in "${batch_files[@]}"; do
                mark_as_processed "$file"
            done
            total_processed=$((total_processed + ${#batch_files[@]}))
        else
            # 失敗した場合の処理
            print_warning "バッチ $iteration で一部ファイルの処理に失敗しました"
            
            # 失敗したファイルも処理済みとしてマーク（無限ループを防ぐ）
            for file in "${batch_files[@]}"; do
                mark_as_processed "$file"
            done
            total_failed=$((total_failed + ${#batch_files[@]}))
        fi
        
        # クリーンアップ
        rm -rf "$batch_input_dir"
        
        # 進行状況の表示
        show_status
        
        # 短時間の休憩（システム負荷軽減）
        print_info "次のバッチまで 10秒待機..."
        sleep 10
        
        ((iteration++))
    done
    
    # 最終結果の表示
    print_success "🏁 バッチ処理が完了しました！"
    print_info "総処理ファイル数: $total_processed"
    print_info "失敗ファイル数: $total_failed"
    print_info "実行した反復回数: $((iteration - 1))"
    
    # 最終進行状況を保存
    save_progress $iteration $total_processed $total_failed 0
}

# メイン処理
case "${1:-}" in
    "status")
        show_status
        ;;
    "resume")
        if load_progress; then
            print_info "中断された処理を再開します..."
            run_repeat_batch $BATCH_SIZE "$LOCATION" $DEFAULT_MAX_ITERATIONS
        else
            print_error "再開する進行状況が見つかりません"
            exit 1
        fi
        ;;
    "reset")
        print_warning "進行状況をリセットします..."
        rm -f $PROGRESS_FILE $PROCESSED_LIST
        rm -rf input_batch_*
        print_success "リセットが完了しました"
        ;;
    "clean")
        print_info "一時ファイルをクリーンアップ中..."
        rm -f $PROGRESS_FILE $PROCESSED_LIST
        rm -rf input_batch_*
        docker-compose -f $COMPOSE_FILE down --remove-orphans 2>/dev/null || true
        print_success "クリーンアップが完了しました"
        ;;
    "help"|"--help"|"-h")
        show_usage
        ;;
    "")
        # デフォルト実行
        run_repeat_batch $DEFAULT_BATCH_SIZE "$DEFAULT_LOCATION" $DEFAULT_MAX_ITERATIONS
        ;;
    *)
        # 引数が数字の場合はバッチサイズとして処理
        if [[ $1 =~ ^[0-9]+$ ]]; then
            run_repeat_batch "$1" "$2" "$3"
        else
            print_error "不明なコマンド: $1"
            show_usage
            exit 1
        fi
        ;;
esac