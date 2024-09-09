from typing import Optional
import numpy as np
import torch
from PIL import Image
from pydantic import BaseModel, Field
from transformers import Owlv2ForObjectDetection, Owlv2Processor

from vision_agent_tools.shared_types import BaseMLModel, Device, VideoNumpy


class OWLV2Config(BaseModel):
    model_name: str = Field(
        default="google/owlv2-large-patch14-ensemble",
        description="Name of the model",
    )
    processor_name: str = Field(
        default="google/owlv2-large-patch14-ensemble",
        description="Name of the processor",
    )
    confidence: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Confidence threshold for model predictions",
    )
    device: Device = Field(
        default=(
            Device.GPU
            if torch.cuda.is_available()
            else Device.MPS if torch.backends.mps.is_available() else Device.CPU
        ),
        description="Device to run the model on. Options are 'cpu', 'gpu', and 'mps'. Default is the first available GPU.",
    )


class Owlv2InferenceData(BaseModel):
    """
    Represents an inference result from the Owlv2 model.
    """

    label: str = Field(description="The predicted label for the detected object")
    score: float = Field(
        description="TThe confidence score associated with the prediction (between 0 and 1)"
    )
    bbox: list[float] = Field(
        description=" A list of four floats representing the bounding box coordinates (xmin, ymin, xmax, ymax) of the detected object in the image"
    )


class Owlv2(BaseMLModel):
    """
    Tool for object detection using the pre-trained Owlv2 model from
    [Transformers](https://github.com/huggingface/transformers).

    This tool takes an image and a list of prompts as input, performs object detection using the Owlv2 model,
    and returns a list of `Owlv2InferenceData` objects containing the predicted labels, confidence scores,
    and bounding boxes for detected objects with confidence exceeding a threshold.
    """

    def __run_inference(self, image, texts, confidence):
        # Run model inference here
        inputs = self._processor(text=texts, images=image, return_tensors="pt").to(
            self.model_config.device
        )
        # Forward pass
        with torch.autocast(self.model_config.device):
            outputs = self._model(**inputs)

        target_sizes = torch.Tensor([image.size[::-1]])

        # Convert outputs (bounding boxes and class logits) to the final predictions type
        results = self._processor.post_process_object_detection(
            outputs=outputs, threshold=confidence, target_sizes=target_sizes
        )
        i = 0  # given that we are predicting on only one image
        boxes, scores, labels = (
            results[i]["boxes"],
            results[i]["scores"],
            results[i]["labels"],
        )

        inferences: list[Owlv2InferenceData] = []
        for box, score, label in zip(boxes, scores, labels):
            box = [round(i, 2) for i in box.tolist()]
            inferences.append(
                Owlv2InferenceData(
                    label=texts[i][label.item()], score=score.item(), bbox=box
                )
            )

        return inferences

    def __init__(self, model_config: Optional[OWLV2Config] = None):
        """
        Initializes the Owlv2 object detection tool.

        Loads the pre-trained Owlv2 processor and model from Transformers.
        """
        self.model_config = model_config or OWLV2Config()
        self._model = Owlv2ForObjectDetection.from_pretrained(
            self.model_config.model_name
        )
        self._processor = Owlv2Processor.from_pretrained(
            self.model_config.processor_name
        )
        self._model.to(self.model_config.device)
        self._model.eval()

    @torch.inference_mode()
    def __call__(
        self,
        prompts: list[str],
        image: Image.Image | None = None,
        video: VideoNumpy[np.uint8] | None = None,
    ) -> list[list[Owlv2InferenceData]]:
        """
        Performs object detection on an image using the Owlv2 model.

        Args:
            image (Image.Image): The input image for object detection.
            prompts (list[str]): A list of prompts to be used during inference.
                                  Currently, only one prompt is supported (list length of 1).
            confidence (Optional[float], defaults=DEFAULT_CONFIDENCE): The minimum confidence threshold for
                                                                          including a detection in the results.

        Returns:
            Optional[list[Owlv2InferenceData]]: A list of `Owlv2InferenceData` objects containing the predicted
                                               labels, confidence scores, and bounding boxes for detected objects
                                               with confidence exceeding the threshold. Returns None if no objects
                                               are detected above the confidence threshold.
        """
        texts = [prompts]

        if image is None and video is None:
            raise ValueError("Either 'image' or 'video' must be provided.")
        if image is not None and video is not None:
            raise ValueError("Only one of 'image' or 'video' can be provided.")

        if image is not None:
            image = image.convert("RGB")
            inferences = []
            inferences.append(
                self.__run_inference(
                    image=image, texts=texts, confidence=self.model_config.confidence
                )
            )
        if video is not None:
            inferences = []
            for frame in video:
                image = Image.fromarray(frame).convert("RGB")
                inferences.append(
                    self.__run_inference(
                        image=image,
                        texts=texts,
                        confidence=self.model_config.confidence,
                    )
                )

        return inferences

    def to(self, device: Device):
        self._model.to(device=device.value)
