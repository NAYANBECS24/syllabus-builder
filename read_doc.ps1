$word = New-Object -ComObject Word.Application
$word.Visible = $false
$filePath = "C:\Users\nayan\Downloads\itech project\syllabus builder\SYLEX_OmegaX_Next_Level_Integrated_Architecture_v2.2_Dual_Mode_LLM_Hardened both system.docx"
$doc = $word.Documents.Open($filePath)
$text = $doc.Content.Text
$doc.Close($false)
$word.Quit()
$text | Out-File -FilePath "C:\Users\nayan\Downloads\itech project\syllabus builder\doc_content.txt" -Encoding UTF8
Write-Host "Done - file written"
