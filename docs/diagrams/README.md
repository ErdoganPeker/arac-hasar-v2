# Diyagram Kütüphanesi — Araç Hasar Tespit v2

Teknik rapor için profesyonel görsel materyaller. Tüm Mermaid kaynakları PDF/HTML render için hazırdır.

## Dosyalar

| Dosya | Tür | İçerik |
|-------|-----|--------|
| `architecture.mmd` | Mermaid flowchart | Sistem mimari diyagramı (Web/Mobile/Desktop -> Gateway -> Backend -> Worker -> ML -> DB) |
| `ml_pipeline.mmd` | Mermaid flowchart | ML Pipeline akışı (paralel YOLO inferans + IoU eşleme + ensemble + cost) |
| `dataset_relations.mmd` | Mermaid flowchart | Veri seti / pre-trained kaynak / model ilişki grafiği |
| `training_timeline.mmd` | Mermaid gantt | 3 model eğitim zaman çizelgesi (~12-16 saat) |
| `performance_table.md` | Markdown tablo | Custom vs pre-trained mAP / latency / boyut karşılaştırma |
| `confusion_matrix.md` | ASCII + Mermaid xychart | Damage / Parts / Severity confusion matrix + sınıf metrikleri |

## Render

```bash
# Mermaid CLI ile PNG
npx -y @mermaid-js/mermaid-cli@latest -i docs/diagrams/architecture.mmd \
  -o docs/diagrams/architecture.png -b transparent -w 1600

# PDF içine direkt embed (markdown-it / pandoc / typst destekler)
```

VSCode'da "Markdown Preview Mermaid Support" eklentisi ile syntax doğrulanabilir.

## Document Generator Kullanımı

Raporda referans:

```markdown
![Sistem Mimarisi](diagrams/architecture.png)
![ML Pipeline](diagrams/ml_pipeline.png)
![Veri Seti Iliskileri](diagrams/dataset_relations.png)
![Egitim Zaman Cizelgesi](diagrams/training_timeline.png)

{{ include: diagrams/performance_table.md }}
{{ include: diagrams/confusion_matrix.md }}
```
