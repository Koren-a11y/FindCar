# FindCar - 二手车监控

一个基于 **carsensor.net** 的简易监控产品，当前目标是：
- 监控车型：**Honda N-VAN**
- 条件：**涡轮增压 + 白色**
- 输出：列表、图片、价格、地点
- 支持按价格和地区进一步缩小范围

## 如何运行和查看（本地）

```bash
python -m venv .venv
source .venv/bin/activate
python scripts/fetch_cars.py --max-price 1500000 --region 東京
python -m http.server 8000
```

打开：`http://localhost:8000/web/`

执行后会产出：
- `data/listings.json`（监控结果数据）

## 如何推送并部署到 GitHub Actions

1. 提交并推送代码：

```bash
git add .
git commit -m "feat: improve monitor and deployment"
git push origin <your-branch>
```

2. 在 GitHub 仓库中启用 Pages：
   - Settings → Pages → Source 选择 **GitHub Actions**。

3. 触发工作流：
   - Actions → `Monitor N-VAN and Deploy` → `Run workflow`
   - 可选输入：
     - `max_price`（JPY）
     - `region`（地区关键字）

4. 部署完成后在 workflow 的 `deploy` job 中查看页面 URL。

## GitHub Actions 自动部署说明

工作流文件：`.github/workflows/monitor-and-deploy.yml`

功能：
1. 每 6 小时抓取一次 carsensor 数据。
2. 将结果写入 `data/listings.json` 并自动提交。
3. 构建并发布到 GitHub Pages（`web/index.html` + 数据文件）。
4. 支持手动触发时传入 `max_price` 和 `region`。

## 注意

- carsensor 页面结构可能变化，若抓取失败请检查 `data/listings.json` 中 `error` 字段。
- 建议根据平台 robots 与使用条款控制抓取频率。
