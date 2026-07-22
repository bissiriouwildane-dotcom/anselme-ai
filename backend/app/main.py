import os
from fastapi import FastAPI, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import edge_tts  # Bibliothèque de synthèse vocale gratuite

app = FastAPI(title="Anselme.AI Backend")

# Configuration du CORS pour autoriser ton téléphone à communiquer avec le serveur
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modèle de données pour recevoir les curseurs
class TTSRequest(BaseModel):
    text: str
    voice_id: str
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"

@app.get("/")
def read_root():
    return {"status": "Anselme.AI API en ligne"}

@app.post("/api/tts")
async def generate_voice(request: TTSRequest):
    # 1. Vérification si le texte est vide
    if not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Le texte est vide."
        )
    
    # 2. Sécurité Anselme.AI : max 10 000 caractères
    if len(request.text) > 10000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sécurité Anselme.AI : Le texte dépasse la limite maximale de 10 000 caractères."
        )

    print(f"--- Nouvelle requête reçue ---")
    print(f"Texte ({len(request.text)} caractères) : {request.text[:50]}...")
    print(f"Données brutes reçues -> Vitesse: {request.rate} | Tonalité: {request.pitch} | Volume: {request.volume}")

    # 🛠️ NETTOYAGE ET FORMATAGE STRICT POUR EDGE-TTS
    
    # Vitesse (Rate) : Forcer le signe si manquant
    rate_param = request.rate if ("%" in request.rate) else f"{request.rate}%"
    if not rate_param.startswith(("-", "+")):
        rate_param = "+" + rate_param

    # Tonalité (Pitch) : Forcer l'unité Hz et le signe
    pitch_param = request.pitch if ("Hz" in request.pitch) else f"{request.pitch}Hz"
    if not pitch_param.startswith(("-", "+")):
        pitch_param = "+" + pitch_param

    # Volume (Gain) : Traitement de la valeur absolue (ex: 79) en variation signée (ex: 79 - 100 = -21%)
    try:
        # On extrait uniquement les chiffres pour calculer l'écart par rapport à 100%
        clean_vol = "".join(c for c in request.volume if c.isdigit() or c == "-")
        vol_numeric = int(clean_vol)
        
        # Si le frontend envoie une valeur brute entre 0 et 100 (comme 77 ou 79)
        if 0 <= vol_numeric <= 100:
            diff = vol_numeric - 100
            volume_param = f"{diff}%" if diff < 0 else "+0%"
        else:
            # Si c'est déjà un format signé (+10% ou -15%)
            volume_param = request.volume if ("%" in request.volume) else f"{request.volume}%"
            if not volume_param.startswith(("-", "+")):
                volume_param = "+" + volume_param
    except Exception:
        # Fallback de sécurité pour le formatage du volume
        volume_param = "+0%"

    print(f"Modulation finale appliquée -> Vitesse: {rate_param} | Tonalité: {pitch_param} | Volume: {volume_param}")

    try:
        # 3. Tentative de génération AVEC les modulations demandées
        communicate = edge_tts.Communicate(
            text=request.text, 
            voice=request.voice_id,
            rate=rate_param,
            pitch=pitch_param,
            volume=volume_param
        )
        
        audio_bytes = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_bytes.extend(chunk["data"])
        
        if not audio_bytes:
            raise ValueError("Flux audio vide reçu avec les modulations.")

    except Exception as e:
        print(f"⚠️ Alerte : Échec avec modulation ({str(e)}). Lancement du plan de secours (Voix brute)...")
        try:
            # PLAN DE SECOURS AUTOMATIQUE : On génère sans modulation pour éviter le crash de l'appli
            communicate = edge_tts.Communicate(text=request.text, voice=request.voice_id)
            audio_bytes = bytearray()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_bytes.extend(chunk["data"])
        except Exception as e_brut:
            print(f"❌ Échec critique (même sans modulation) : {str(e_brut)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Erreur Microsoft TTS : {str(e_brut)}"
            )

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La génération audio a échoué."
        )
        
    print(f"Succès ! Envoi du fichier audio au téléphone ({len(audio_bytes)} octets)")
    return Response(content=bytes(audio_bytes), media_type="audio/mpeg")