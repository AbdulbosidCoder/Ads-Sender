from PIL import Image, ImageDraw, ImageFont

async def write_number_on_image(image_path, number, position=(10, 10), font_size=100):
    # Open the image
    img = Image.open(image_path)

    # Create a draw object
    draw = ImageDraw.Draw(img)

    # Set the font (you can change the font or font size here)
    try:
        # Change "arial.ttf" to the path of your desired TrueType font.
        font = ImageFont.truetype("arial.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
        print("""Error""")
    # Write the number on the image at the specified position
    draw.text(position, str(number), font=font, fill=(0, 0, 0))  # white text color

    # Save or show the image
    img.save(image_path)  # Save the image with the number on it

