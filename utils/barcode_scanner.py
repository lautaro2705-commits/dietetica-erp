"""
utils/barcode_scanner.py - Componente HTML/JS para escaneo de códigos de barras via cámara.
Usa la librería html5-qrcode (CDN) embebida en st.components.v1.html().
"""


def get_barcode_scanner_html(component_key: str = "barcode_scanner") -> str:
    """Retorna el HTML/JS del scanner de códigos de barras.

    El componente comunica el código escaneado via window.parent.postMessage
    y también escribe en un query param para que Streamlit pueda leerlo.
    """
    return f"""
    <div id="scanner-container" style="width:100%;max-width:400px;margin:0 auto;">
        <div id="reader" style="width:100%;"></div>
        <div id="result" style="
            text-align:center; padding:10px; margin-top:10px;
            font-family: sans-serif; font-size:14px; color:#333;
        ">
            Apuntá la cámara al código de barras...
        </div>
    </div>

    <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
    <script>
        const html5QrCode = new Html5Qrcode("reader");
        let lastCode = "";
        let scanning = true;

        function onScanSuccess(decodedText, decodedResult) {{
            if (!scanning || decodedText === lastCode) return;
            lastCode = decodedText;
            scanning = false;

            document.getElementById("result").innerHTML =
                '<span style="color:green; font-weight:bold;">✅ Código: ' + decodedText + '</span>';

            // Comunicar a Streamlit via postMessage
            window.parent.postMessage({{
                type: "barcode_scan",
                code: decodedText,
                key: "{component_key}"
            }}, "*");

            // Pausar brevemente y reactivar el scan
            setTimeout(() => {{
                scanning = true;
                lastCode = "";
            }}, 3000);
        }}

        function onScanFailure(error) {{
            // Silenciar errores de no-detección (son normales)
        }}

        html5QrCode.start(
            {{ facingMode: "environment" }},
            {{
                fps: 10,
                qrbox: {{ width: 250, height: 150 }},
                aspectRatio: 1.777,
            }},
            onScanSuccess,
            onScanFailure
        ).catch(err => {{
            document.getElementById("result").innerHTML =
                '<span style="color:red;">⚠️ No se pudo acceder a la cámara.<br>' +
                'Asegurate de dar permiso de cámara al navegador.</span>';
        }});
    </script>
    """


def get_scanner_height() -> int:
    """Altura recomendada para el componente iframe."""
    return 420
