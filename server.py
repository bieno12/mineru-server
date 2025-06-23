import sys
sys.path.insert(0, '/kaggle/working/mineru-server')

import progress_monitor

import litserve as ls
import uvicorn
from fastapi import Depends, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from pydantic import BaseModel
from typing import Any, Optional, List, Dict
import base64, mimetypes

progress_monitor.patch_tqdm()

from magic_pdf.data.data_reader_writer import FileBasedDataWriter, FileBasedDataReader
from magic_pdf.data.dataset import PymuDocDataset
from magic_pdf.model.doc_analyze_by_custom_model import doc_analyze
from magic_pdf.config.enums import SupportedPdfParseMethod
from in_memory_writer import InMemoryDataWriter
import json


class ImageAPI(ls.LitAPI):
    def setup(self, device):
        self.poll_interval = 1.0
        self.image_writer = InMemoryDataWriter()
    def decode_request(self, request):
        print(request['file'].filename)
        pdf_bytes = request['file'].file.read()

        ## Create Dataset Instance
        ds = PymuDocDataset(pdf_bytes)
        # Open and return the uploaded image file
        args = {
            'dataset': ds,
            'start_page_id': request.get('start_page_id', 0),
            'end_page_id': request.get('end_page_id', None),
            'lang': request.get('lang', None),
            'formula_enable': request.get('formula_enable', None),
            'table_enable': request.get('table_enable', None),
            'return_markdown': request.get('return_markdown', False)
        }
        return args

    def predict(self, args):
        self.image_writer.clear()
        breturn_markdown = args.pop('return_markdown')
        def infer():
            ds = args.pop('dataset')
            
            if ds.classify() == SupportedPdfParseMethod.OCR:
                infer_result = doc_analyze(ds, ocr=True)

                ## pipeline
                pipe_result = infer_result.pipe_ocr_mode(self.image_writer)

            else:
                infer_result = doc_analyze(ds, ocr=False)
                pipe_result = infer_result.pipe_txt_mode(self.image_writer)
            return pipe_result
        update = {}
        for update in progress_monitor.run_with_progress(infer, poll_interval=self.poll_interval):
            if update['status'] != 'completed':
                yield {
                    'type': 'progress',
                    'data': update,
                }
            else: break
            
        pipe_result = update.pop('result')
        content_list = pipe_result.get_content_list("")
        self._encode_images(content_list)
        
        yield {
             "type": "progress",
             "data": update
         }
         
        result = {
            'type': 'result',
            'data': {
                "content_list": content_list,
            },
        }
        
        if breturn_markdown:
            result['data']['markdown'] = pipe_result.get_markdown("")
            
        yield result

    def encode_response(self, chunks):
        for chunk in chunks:
            # Serialize in the most compact single-line form:
            line = json.dumps(chunk, ensure_ascii=False, separators=(',', ':'))
            # Then terminate with exactly one '\n'
            yield line + "\n"

    def authorize(self, auth: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
        if auth.scheme != "Bearer" or auth.credentials != "secret_key":
            raise HTTPException(status_code=401, detail="Bad token")
        
    def _encode_images(self, content_list: List[Dict]) -> None:
        """
        Enhanced version with better error handling and MIME type detection.
        
        Args:
            content_list: List of content items, some may have type "image"
        """
        
        for item in content_list:
            if item.get('type') in ['image', 'table']:
                image_path = item.pop('img_path')
                if image_path.startswith('/'):
                    image_path = image_path[1:]
                
                if image_path:
                    try:
                        # Read the image data from the in-memory writer
                        image_bytes = self.image_writer.read(image_path)
                        
                        if image_bytes:
                            # Encode to base64
                            base64_data = base64.b64encode(image_bytes).decode('utf-8')
                            
                            # Optionally detect MIME type and create data URL
                            mime_type, _ = mimetypes.guess_type(image_path)
                            if mime_type and mime_type.startswith('image/'):
                                # Create a data URL format: data:image/png;base64,<base64_data>
                                item['img_url'] = f"data:{mime_type};base64,{base64_data}"
                            
                        else:
                            print(f"Warning: Image data not found for path: {image_path}")
                            item['img_url'] = None
                            
                    except Exception as e:
                        print(f"Error encoding image {image_path}: {str(e)}")
                        item['img_url'] = None
                else:
                    print(f"Warning: No image path found in item: {item}")
                    item['img_url'] = None
                    
if __name__ == '__main__':
    api = ImageAPI(stream=True)
    server = ls.LitServer(api)
    server.run("0.0.0.0", 8000, reload=False)
