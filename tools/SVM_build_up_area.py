import rasterio
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC
from sklearn.metrics import classification_report, accuracy_score, cohen_kappa_score, confusion_matrix
def train_svm_optimized(X, y):
    # 1. 划分训练集和测试集 (80% 训练, 20% 测试)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 2. 特征标准化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # 3. 初始化 SVM 模型
    # class_weight='balanced' 会自动平衡 0 和 1 的权重
    print("正在训练 SVM 模型 (包含类别权重优化)...")
    model = SVC(kernel='rbf', C=2, gamma=1, class_weight={0: 1, 1: 1}, 
                verbose=True, cache_size=4000)
    model.fit(X_train_scaled, y_train)
    
    # 4. 评估
    y_pred = model.predict(X_test_scaled)
    
    print("\n" + "="*30)
    print("      模型评估报告")
    print("="*30)
    print(f"总体准确率 (Accuracy): {accuracy_score(y_test, y_pred):.4f}")
    print(f"Kappa 系数: {cohen_kappa_score(y_test, y_pred):.4f}")
    print("\n分类详细指标:")
    print(classification_report(y_test, y_pred, target_names=['非建成区(0)', '建成区(1)']))
    
    print("混淆矩阵:")
    print(confusion_matrix(y_test, y_pred))
    
    return model, scaler

def load_and_preprocess(ntl_path, mgup_path):
    """
    读取夜间灯光和建成区标签数据，处理空值并对齐
    """
    with rasterio.open(ntl_path) as src_ntl:
        ntl_data = src_ntl.read(1).astype('float32')
        ntl_meta = src_ntl.meta
        ntl_nodata = src_ntl.nodata

    with rasterio.open(mgup_path) as src_mgup:
        mgup_data = src_mgup.read(1).astype('float32')
        mgup_nodata = src_mgup.nodata

    # 1. 创建掩膜：处理 NoData
    # 假设背景值为负值、特定nodata值或极大的异常值
    mask = (ntl_data != ntl_nodata) & (mgup_data != mgup_nodata) & (~np.isnan(ntl_data)) & (~np.isnan(mgup_data))
    
    # 进一步排除常见的背景值（根据您的描述，NTL是0-255，MGUP是0,1，如果背景是0也要排除，请根据实际情况调整）
    # 这里我们只排除 metadata 定义的 nodata
    
    # 2. 提取有效样本
    X = ntl_data[mask].reshape(-1, 1) # SVM 需要二维数组 (n_samples, n_features)
    y = mgup_data[mask].astype('int')
    
    # 3. 统计输出
    n_samples = len(y)
    n_built = np.sum(y == 1)
    n_non_built = np.sum(y == 0)
    
    print(f"有效样本数: {n_samples}")
    print(f"建成区样本(1): {n_built}, 非建成区(0): {n_non_built}")
    
    # 返回训练用的X,y，以及用于后续还原影像的原始数据和元数据
    return X, y, ntl_data, mask, ntl_meta

import rasterio
import numpy as np

def predict_and_save(model, scaler, full_ntl, mask, meta, output_path):
    """
    使用训练好的模型对整幅影像进行预测并保存
    """
    print("\nStep 3: 准备全图预测数据...")
    
    # 1. 提取所有掩膜内的有效像素进行预测
    X_full = full_ntl[mask].reshape(-1, 1)
    
    # 2. 必须使用训练时同样的 scaler 进行标准化
    X_full_scaled = scaler.transform(X_full)
    
    # 3. 预测
    print("正在进行 SVM 全图分类预测 (这可能需要一点时间)...")
    y_full_pred = model.predict(X_full_scaled)
    
    # 4. 将一维预测结果还原为二维矩阵
    # 初始化一个全为背景值（nodata）的矩阵
    # 我们用 -1 代表预测范围外的区域，0和1代表分类结果
    result_img = np.full(full_ntl.shape, -1, dtype='int16')
    result_img[mask] = y_full_pred
    
    # 5. 更新元数据并保存
    # 修改 dtype 为 int16, nodata 为 -1
    out_meta = meta.copy()
    out_meta.update({
        "driver": "GTiff",
        "dtype": 'int16',
        "count": 1,
        "nodata": -1
    })
    
    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(result_img.astype('int16'), 1)
    
    print(f"恭喜！预测结果已成功保存至: {output_path}")

import joblib

# ==========================================
# 1. (补充) 如何保存模型
# ==========================================
def save_trained_model(model, scaler, model_path, scaler_path):
    joblib.dump(model, model_path)
    joblib.dump(scaler, scaler_path)
    print(f"模型已保存至: {model_path}")
    print(f"标准化工具已保存至: {scaler_path}")

# ==========================================
# 2. 对新区域进行预测并验证
# ==========================================
def predict_and_verify(model, scaler, new_ntl_path, real_label_path, output_path):
    print("\n--- 开始对新区域进行预测与验证 ---")
    
    # 读取数据
    with rasterio.open(new_ntl_path) as src_ntl:
        ntl_sh = src_ntl.read(1).astype('float32')
        meta = src_ntl.meta
        nodata_ntl = src_ntl.nodata

    with rasterio.open(real_label_path) as src_real:
        real_sh = src_real.read(1).astype('int16')
        nodata_real = src_real.nodata

    # 创建掩膜：排除两个文件中的空值
    mask = (ntl_sh != nodata_ntl) & (real_sh != nodata_real) & (~np.isnan(ntl_sh))
    
    # 提取有效数据并标准化
    X_new = ntl_sh[mask].reshape(-1, 1)
    X_new_scaled = scaler.transform(X_new) # 必须使用训练时的 scaler!
    
    # 真实标签
    y_true = real_sh[mask]

    # 执行预测
    print("正在分类中...")
    y_pred = model.predict(X_new_scaled)

    # 计算精度
    oa = accuracy_score(y_true, y_pred)
    kappa = cohen_kappa_score(y_true, y_pred)
    
    print("\n" + "="*30)
    print(f"新区域验证结果 (SH)")
    print("="*30)
    print(f"总体准确率 (Overall Accuracy): {oa:.4f}")
    print(f"Kappa 系数: {kappa:.4f}")
    print("\n详细分类报告:")
    print(classification_report(y_true, y_pred))

    # 保存预测出的 TIF 影像
    result_img = np.full(ntl_sh.shape, -1, dtype='int16')
    result_img[mask] = y_pred
    
    out_meta = meta.copy()
    out_meta.update(dtype='int16', count=1, nodata=-1)
    
    with rasterio.open(output_path, "w", **out_meta) as dest:
        dest.write(result_img, 1)
    
    print(f"预测影像已保存至: {output_path}")



# --- 执行预测 ---
# output_file = r'C:\NTL-CHAT\tool\SVM_Build_up_area\cities_built_up_predicted.tif'
# predict_and_save(model, scaler, full_ntl, mask, meta, output_file)

# 测试代码 (在您的本地环境下运行)
if __name__ == "__main__":
    import joblib
    import os

    # 定义路径
    base_path = r'./example/SVM_Build_up_area'
    ntl_file = os.path.join(base_path, 'cities_ntl_mask.tif')
    mgup_file = os.path.join(base_path, 'cities_MGUP_mask.tif')
    
    model_save_path = os.path.join(base_path, 'svm_built_up_model.joblib')
    scaler_save_path = os.path.join(base_path, 'svm_scaler.joblib')
    output_tif = os.path.join(base_path, 'cities_built_up_predicted.tif')

    sh_ntl_file = os.path.join(base_path, 'predict_sh.tif')
    sh_real_file = os.path.join(base_path, 'real_sh.tif')
    sh_output_file = os.path.join(base_path, 'sh_predicted_result6.tif')

    model_path = r'./example/SVM_Build_up_area/svm_built_up_model.joblib'
    scaler_path = r'./example/SVM_Build_up_area/svm_scaler.joblib'

    try:
        # # 1. 加载与训练
        # X, y, full_ntl, mask, meta = load_and_preprocess(ntl_file, mgup_file)
        # model, scaler = train_svm_optimized(X, y)
        
        # # 2. 【核心】保存模型和 Scaler
        # print("\n正在保存模型...")
        # joblib.dump(model, model_save_path)
        # joblib.dump(scaler, scaler_save_path)
        # print(f"模型保存成功！")

        # # 3. 执行预测并导出
        # predict_and_save(model, scaler, full_ntl, mask, meta, output_tif)
        #     # 定义上海区域的文件路径
        print("正在从硬盘加载模型和标准化工具...")
        model = joblib.load(model_path)
        scaler = joblib.load(scaler_path)
        predict_and_verify(model, scaler, sh_ntl_file, sh_real_file, sh_output_file)
        
    except Exception as e:
        print(f"操作失败: {e}")

    