import face_recognition
import numpy as np

def get_face_encoding(image_path):
    image = face_recognition.load_image_file(image_path)
    encodings = face_recognition.face_encodings(image)
    if len(encodings) == 0:
        return None
    return encodings[0]

def match_face(unknown_encoding, known_encodings, known_ids, tolerance=0.5):
    if not known_encodings:
        return None

    distances = face_recognition.face_distance(known_encodings, unknown_encoding)
    min_distance_index = np.argmin(distances)

    if distances[min_distance_index] <= tolerance:
        return known_ids[min_distance_index]
    return None
