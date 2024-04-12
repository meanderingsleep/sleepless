from dotenv import load_dotenv
import os
from openai import OpenAI
import io
from pathlib import Path
from freeplay import Freeplay 
from freeplay.provider_config import ProviderConfig, OpenAIConfig
import requests
from botocore.exceptions import NoCredentialsError
from pydub import AudioSegment
from ffmpeg import FFmpeg
import utils
import sys
from datetime import date
import datetime
import time

load_dotenv() 

# make sure the correct number of arguments were passed in.
# i now want voice and story type passed in 
try:
    len(sys.argv) == 4
    loopCount = sys.argv[1]
    promptType = sys.argv[2] 
    voiceType = sys.argv[3]
    print("Looping: " + sys.argv[1] + " times" + "\n" + "Prompt: " + sys.argv[2] + "\n" + "Voice: " + sys.argv[3])
except:
    print("Usage: " + sys.argv[0] + " loopCount")
    sys.exit()

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
tts_url = f'https://api.elevenlabs.io/v1/text-to-speech/{voiceType}'
CHUNK_SIZE = 1024

# Freeplay prompting configuration
freeplay_chat = Freeplay(
    provider_config=ProviderConfig(openai=OpenAIConfig(os.environ['OPENAI_API_KEY'])),
    freeplay_api_key=os.environ['FREEPLAY_API_KEY'],
    api_base=f'https://{os.environ["FREEPLAY_CUSTOMER_NAME"]}.freeplay.ai/api')

freeplay_environment = os.environ.get("FREEPLAY_ENVIRONMENT")

merged = AudioSegment.empty()
context=""
i = 0

# Generate chunks of text/audio
while i < int(loopCount): 
    story = freeplay_chat.get_completion(
        project_id=os.environ['FREEPLAY_PROJECT_ID'],
        template_name=promptType,
        variables={"context":context},
        tag=freeplay_environment
    )

    context = utils.getLast20Words(story.content)

    prevTime = datetime.datetime.now()

    headers = {
    "Accept": "application/json",
    "xi-api-key": os.environ['XI_API_KEY']
    }

    data = {
        "text": story.content,
        "model_id": "eleven_turbo_v2",
        "voice_settings": {
            "stability": 0.9,
            "similarity_boost": 0.9,
            "style": 0.0,
            "use_speaker_boost": True
            }
    }

    response = requests.post(tts_url, headers=headers, json=data, stream=True)

    if response.ok:
        with open(f"temp_output{i}.mp3", "wb") as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                f.write(chunk)
    else:
        print(response.text)

    # do some rudimentary rate limiting
    ttsCallsPerMinute = 3
    if (datetime.datetime.now() - prevTime).seconds < (60/ttsCallsPerMinute):
        time.sleep(60-(60/ttsCallsPerMinute))

    merged += AudioSegment.from_file(Path(__file__).parent / f'temp_output{i}.mp3')
    i += 1

# Export final file to cloud and cleanup temp files
finalOutputFilename = f"sleepless-{date.today()}.mp3"
finalOutputPath = Path(__file__).parent / finalOutputFilename
merged.export(finalOutputPath, format="mp3", bitrate="192k")

uploaded = utils.upload_to_aws(finalOutputPath, 
    os.environ.get("AWS_S3_BUCKET"), 
    finalOutputFilename)

utils.deleteTempMp3(loopCount)
#os.remove(finalOutputPath)