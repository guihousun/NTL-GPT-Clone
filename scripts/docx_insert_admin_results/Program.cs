using System.Globalization;
using System.IO.Packaging;
using System.Text;
using DocumentFormat.OpenXml;
using DocumentFormat.OpenXml.Packaging;
using DocumentFormat.OpenXml.Wordprocessing;
using A = DocumentFormat.OpenXml.Drawing;
using DW = DocumentFormat.OpenXml.Drawing.Wordprocessing;
using PIC = DocumentFormat.OpenXml.Drawing.Pictures;

static string Arg(string[] args, string name, string fallback = "")
{
    for (var i = 0; i < args.Length - 1; i++)
        if (args[i] == name)
            return args[i + 1];
    return fallback;
}

static List<Dictionary<string, string>> ReadCsv(string path)
{
    var lines = File.ReadAllLines(path, Encoding.UTF8);
    if (lines.Length == 0) return [];
    var headers = ParseCsvLine(lines[0]);
    var rows = new List<Dictionary<string, string>>();
    foreach (var line in lines.Skip(1))
    {
        if (string.IsNullOrWhiteSpace(line)) continue;
        var cells = ParseCsvLine(line);
        var row = new Dictionary<string, string>();
        for (var i = 0; i < headers.Count; i++)
            row[headers[i]] = i < cells.Count ? cells[i] : "";
        rows.Add(row);
    }
    return rows;
}

static List<string> ParseCsvLine(string line)
{
    var cells = new List<string>();
    var sb = new StringBuilder();
    var quoted = false;
    for (var i = 0; i < line.Length; i++)
    {
        var ch = line[i];
        if (ch == '"')
        {
            if (quoted && i + 1 < line.Length && line[i + 1] == '"')
            {
                sb.Append('"');
                i++;
            }
            else
            {
                quoted = !quoted;
            }
        }
        else if (ch == ',' && !quoted)
        {
            cells.Add(sb.ToString());
            sb.Clear();
        }
        else
        {
            sb.Append(ch);
        }
    }
    cells.Add(sb.ToString());
    return cells;
}

static string Fmt(string value, int digits = 2)
{
    if (double.TryParse(value, NumberStyles.Any, CultureInfo.InvariantCulture, out var v))
    {
        if (double.IsNaN(v) || double.IsInfinity(v)) return "NA";
        return v.ToString("F" + digits, CultureInfo.InvariantCulture);
    }
    return string.IsNullOrWhiteSpace(value) ? "NA" : value;
}

static Paragraph P(string text, string? style = null, JustificationValues? align = null)
{
    var paragraph = new Paragraph();
    if (style != null || align != null)
    {
        var pPr = new ParagraphProperties();
        if (style != null) pPr.Append(new ParagraphStyleId { Val = style });
        if (align != null) pPr.Append(new Justification { Val = align.Value });
        paragraph.Append(pPr);
    }
    paragraph.Append(new Run(new Text(text) { Space = SpaceProcessingModeValues.Preserve }));
    return paragraph;
}

static Table T(string[] headers, IEnumerable<string[]> rows)
{
    var table = new Table();
    table.Append(new TableProperties(
        new TableBorders(
            new TopBorder { Val = BorderValues.Single, Size = 6 },
            new BottomBorder { Val = BorderValues.Single, Size = 6 },
            new LeftBorder { Val = BorderValues.Single, Size = 6 },
            new RightBorder { Val = BorderValues.Single, Size = 6 },
            new InsideHorizontalBorder { Val = BorderValues.Single, Size = 4 },
            new InsideVerticalBorder { Val = BorderValues.Single, Size = 4 }
        ),
        new TableWidth { Width = "5000", Type = TableWidthUnitValues.Pct }
    ));
    table.Append(Row(headers, true));
    foreach (var r in rows) table.Append(Row(r, false));
    return table;
}

static TableRow Row(IEnumerable<string> cells, bool header)
{
    var row = new TableRow();
    foreach (var text in cells)
    {
        var p = P(text);
        if (header)
        {
            var run = p.GetFirstChild<Run>();
            run?.PrependChild(new RunProperties(new Bold()));
        }
        row.Append(new TableCell(p));
    }
    return row;
}

static Paragraph ImageParagraph(MainDocumentPart mainPart, string imagePath, string relationshipId, long cx, long cy)
{
    var imagePart = mainPart.AddImagePart(ImagePartType.Png);
    using (var stream = File.OpenRead(imagePath))
        imagePart.FeedData(stream);
    var relId = mainPart.GetIdOfPart(imagePart);
    var drawing = new Drawing(
        new DW.Inline(
            new DW.Extent { Cx = cx, Cy = cy },
            new DW.EffectExtent { LeftEdge = 0L, TopEdge = 0L, RightEdge = 0L, BottomEdge = 0L },
            new DW.DocProperties { Id = UInt32Value.FromUInt32(1U), Name = relationshipId },
            new DW.NonVisualGraphicFrameDrawingProperties(new A.GraphicFrameLocks { NoChangeAspect = true }),
            new A.Graphic(
                new A.GraphicData(
                    new PIC.Picture(
                        new PIC.NonVisualPictureProperties(
                            new PIC.NonVisualDrawingProperties { Id = UInt32Value.FromUInt32(0U), Name = Path.GetFileName(imagePath) },
                            new PIC.NonVisualPictureDrawingProperties()
                        ),
                        new PIC.BlipFill(
                            new A.Blip { Embed = relId },
                            new A.Stretch(new A.FillRectangle())
                        ),
                        new PIC.ShapeProperties(
                            new A.Transform2D(
                                new A.Offset { X = 0L, Y = 0L },
                                new A.Extents { Cx = cx, Cy = cy }
                            ),
                            new A.PresetGeometry(new A.AdjustValueList()) { Preset = A.ShapeTypeValues.Rectangle }
                        )
                    )
                )
                { Uri = "http://schemas.openxmlformats.org/drawingml/2006/picture" }
            )
        )
        {
            DistanceFromTop = 0U,
            DistanceFromBottom = 0U,
            DistanceFromLeft = 0U,
            DistanceFromRight = 0U
        }
    );
    return new Paragraph(new ParagraphProperties(new Justification { Val = JustificationValues.Center }), new Run(drawing));
}

static int FindHeadingIndex(List<OpenXmlElement> elements, string text)
{
    for (var i = 0; i < elements.Count; i++)
    {
        if (elements[i] is Paragraph p && p.InnerText.Trim() == text)
            return i;
    }
    return -1;
}

var input = Arg(args, "--input");
var output = Arg(args, "--output");
var dataDir = Arg(args, "--data-dir");
if (string.IsNullOrWhiteSpace(input) || string.IsNullOrWhiteSpace(output) || string.IsNullOrWhiteSpace(dataDir))
    throw new ArgumentException("Required args: --input <docx> --output <docx> --data-dir <dir>");

File.Copy(input, output, true);

var adm1Counts = ReadCsv(Path.Combine(dataDir, "adm1_attack_counts_iran_israel.csv")).Take(10).ToList();
var adm2Counts = ReadCsv(Path.Combine(dataDir, "adm2_attack_counts_iran_israel.csv")).Take(10).ToList();
var adm1Impact = ReadCsv(Path.Combine(dataDir, "adm1_top10_impact_summary.csv"));
var adm2Impact = ReadCsv(Path.Combine(dataDir, "adm2_top10_impact_summary.csv"));
var figAdm1 = Path.Combine(dataDir, "fig_adm1_top10_ntl_curves.png");
var figAdm2 = Path.Combine(dataDir, "fig_adm2_top10_ntl_curves.png");

using var doc = WordprocessingDocument.Open(output, true);
var main = doc.MainDocumentPart ?? throw new InvalidOperationException("Missing main document part.");
var body = main.Document.Body ?? throw new InvalidOperationException("Missing body.");
var children = body.Elements().ToList();
var start = FindHeadingIndex(children, "IV. RESULTS AND DISCUSSION");
var end = FindHeadingIndex(children, "V. CONCLUSION");
if (start < 0 || end < 0 || end <= start) throw new InvalidOperationException("Could not locate IV/V headings.");

var section = new List<OpenXmlElement>
{
    P("IV. RESULTS AND DISCUSSION", "Heading1"),
    P("A. 事件检索与筛选结果", "Heading2"),
    P("当前 ConflictNTL 工作流已经完成事件检索、事件筛选、行政区 AOI 构建、官方 VNP46A1 数据下载和行政区夜光统计。实验窗口内共提取 3,093 条 ISW 事件记录，其中 3,008 条通过第一阶段来源和几何筛选，1,420 条进入夜光候选队列，伊朗和以色列境内候选事件为 1,235 条。"),
    T(["阶段", "当前结果"], new[]
    {
        new[] {"实验窗口内 ISW 事件记录", "3,093"},
        new[] {"第一阶段候选点", "3,008"},
        new[] {"第二阶段候选点", "1,420"},
        new[] {"伊朗/以色列主体分析候选事件", "1,235"},
        new[] {"Iran/Israel VNP46A1 HDF5 granules", "368"},
        new[] {"ADM1 top-10 日尺度统计有效区域", "8/10"},
        new[] {"ADM2 top-10 日尺度统计有效区域", "8/10"}
    }),
    P("表 III. ConflictNTL pipeline 输出和行政区夜光统计输入。", null, JustificationValues.Center),
    P("B. 行政区聚合分析", "Heading2"),
    P("表 IV 和表 V 分别列出伊朗和以色列累计候选受袭击点最多的前 10 个省级和市级行政区。省级统计中，Tehran、Northern District、Hormozgan 和 Isfahan 是事件最集中的区域；市级统计中，City of Tehran、Zefat 和 Akko 排名靠前。该统计基于所有进入夜光候选队列的受袭击点，并通过空间连接匹配到 geoBoundaries 行政区边界。"),
    T(["ADM1", "国家", "候选事件数"], adm1Counts.Select(r => new[] { r["admin_name"], r["country"], r["candidate_event_count"] })),
    P("表 IV. Iran/Israel 累计候选受袭击点最多的前 10 个 ADM1 行政区。", null, JustificationValues.Center),
    T(["ADM2", "国家", "候选事件数"], adm2Counts.Select(r => new[] { r["admin_name"], r["country"], r["candidate_event_count"] })),
    P("表 V. Iran/Israel 累计候选受袭击点最多的前 10 个 ADM2 行政区。", null, JustificationValues.Center),
    P("C. 行政区夜光变化曲线", "Heading2"),
    P("图 3 和图 4 展示了 top-10 ADM1 和 ADM2 行政区在 2026-02-20 至 2026-04-07 期间的日尺度 VNP46A1 平均夜光曲线。红色虚线表示 2026-02-28 空袭开始日。统计采用 balanced QA，并要求 AOI-day 的有效像元比例不低于 0.80；低于该门槛的日期从曲线和变化率计算中剔除。"),
    ImageParagraph(main, figAdm1, "ADM1 top10 NTL curves", 5400000L, 6200000L),
    P("图 3. ADM1 top-10 行政区的日尺度 VNP46A1 NTL 曲线。", null, JustificationValues.Center),
    ImageParagraph(main, figAdm2, "ADM2 top10 NTL curves", 5400000L, 6200000L),
    P("图 4. ADM2 top-10 行政区的日尺度 VNP46A1 NTL 曲线。", null, JustificationValues.Center),
    P("D. 行政区夜光变化摘要", "Heading2"),
    P("表 VI 和表 VII 汇总了通过 0.80 有效像元比例门槛后的行政区夜光变化。基线期定义为 2026-02-20 至 2026-02-27，冲突期定义为 2026-02-28 至 2026-04-07。需要注意，Tehran 省和 City of Tehran 等核心区域在严格质量门槛下大量日期被标记为 quality rejected，因此当前表格更适合展示可用观测下的候选夜光响应，而不应解释为确认损伤或因果归因。"),
    T(["ADM1", "国家", "事件数", "基线天数", "冲突期天数", "基线均值", "冲突期均值", "变化率%"],
        adm1Impact.Select(r => new[]
        {
            r["admin_name"], r["country"], r["candidate_event_count"], r["baseline_valid_days"],
            r["event_period_valid_days"], Fmt(r["baseline_mean"]), Fmt(r["event_period_mean"]), Fmt(r["delta_pct"])
        })),
    P("表 VI. ADM1 top-10 行政区中通过质量控制区域的 VNP46A1 变化摘要。", null, JustificationValues.Center),
    T(["ADM2", "国家", "事件数", "基线天数", "冲突期天数", "基线均值", "冲突期均值", "变化率%"],
        adm2Impact.Select(r => new[]
        {
            r["admin_name"], r["country"], r["candidate_event_count"], r["baseline_valid_days"],
            r["event_period_valid_days"], Fmt(r["baseline_mean"]), Fmt(r["event_period_mean"]), Fmt(r["delta_pct"])
        })),
    P("表 VII. ADM2 top-10 行政区中通过质量控制区域的 VNP46A1 变化摘要。", null, JustificationValues.Center),
    P("E. 讨论与局限", "Heading2"),
    P("当前行政区统计表明，ConflictNTL 能够将事件流转化为可审计的行政区夜光时间序列，并输出质量控制后的候选变化信号。结果中部分区域表现为夜光增加，这可能与火光、燃烧、工业活动、临时照明、月光/云掩膜残余影响或 AOI 内非受击区域背景变化有关。相反，部分区域缺少足够有效观测，主要是严格 0.80 有效像元比例门槛剔除了云、阴影、雪冰和 DNB 质量异常影响下的 AOI-day。因此，本文将这些结果解释为 source-aligned candidate NTL change signals，而不是确认的冲突损伤。")
};

for (var i = end - 1; i >= start; i--)
    children[i].Remove();

var insertionPoint = body.Elements().ElementAtOrDefault(start);
if (insertionPoint == null)
{
    foreach (var e in section) body.Append(e);
}
else
{
    foreach (var e in section)
        body.InsertBefore(e, insertionPoint);
}

main.Document.Save();
