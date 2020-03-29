import os
from jinja2 import Environment, FileSystemLoader, select_autoescape, Template
from mikula.implementation import settings

GALLERY = settings.gallery_dir
IMAGES = settings.images_dir
THUMBNAILS = settings.thumbnails_dir
USER_ASSETS = settings.user_assets_dir


def cum_sum(x):
    if len(x) == 0:
        return [0.0]

    cs = [0.0] * (len(x))
    cs[0] = x[0]
    for k in range(1, len(cs)):
        cs[k] = cs[k-1] + x[k]
    return cs


def find_closest(x, val):
    min_diff = 1e20
    index = 0
    for k in range(len(x)):
        diff = abs(x[k] - val)
        if diff < min_diff:
            min_diff = diff
            index = k
    return x[index]


def maximum_height(cumulative, columns):
    total = cumulative[-1]
    ideal = total / columns
    previous = 0
    max_height = 0
    for k in range(columns):
        boundary = ideal * (k+1)
        height = find_closest(cumulative, boundary) - previous
        previous = height + previous
        if height > max_height:
            max_height = height
    return max_height


def calculate_heights(aspects, max_columns=3):
    cs = cum_sum(aspects)
    heights = [0.0] * max_columns
    for c in range(max_columns):
        heights[c] = maximum_height(cs, c+1)
    return heights


def parse_subdirectories(album, keys, index):
    output = list()
    current = keys[index]
    relative, subdirectories, _, album_meta, album_md = album[current]
    for directory in subdirectories:
        key = os.path.normpath(os.path.join(current, directory))
        _, _, _, meta, _ = album[key]
        title = meta.get("title", directory)
        order = meta.get("order", -1)
        url = os.path.join(directory, "index.html")
        thumbnail_filename = meta.get("thumbnail", None)
        if thumbnail_filename is not None:
            thumbnail_url = os.path.join(relative, GALLERY, IMAGES, THUMBNAILS, thumbnail_filename)
        else:
            thumbnail_url = None
        output.append((order, title, url, thumbnail_url))
    ordered = sorted(output, key=lambda x: x[0])  # sort by order
    ordered = [(t, u, thu) for _, t, u, thu in ordered]   # re-assemble without order
    return relative, ordered, album_meta, album_md


def parse_images(album, keys, index):
    output = list()
    relative, _, image_files, *rest = album[keys[index]]
    aspects = list()
    for original, (image_file, image_meta, _, aspect) in image_files.items():
        image_name = image_meta["title"]
        image_url = f"{image_meta['basename']}.html"
        thumbnail_url = os.path.join(relative, GALLERY, IMAGES, THUMBNAILS, image_file)
        output.append((image_name, image_url, os.path.normpath(thumbnail_url)))
        aspects.append(aspect)
    return output, aspects


def parent_album(index, length):
    if index < length - 1:
        return "../index.html"
    return None


def render_album_page(album, keys, index, template, page_list, config):
    gallery_root, child_albums, meta, content = parse_subdirectories(album, keys, index)
    thumbnails, aspects = parse_images(album, keys, index)
    max_columns = config.get("max_columns", 1)
    heights = calculate_heights(aspects, max_columns)
    padding = config.get("padding", 0.1)
    user_content = Template(content)
    if "page_title" not in meta.keys():
        meta["page_title"] = meta.get("title", "")
    meta["assets"] = os.path.join(gallery_root, USER_ASSETS)
    html = template.render(page_list_=page_list,
                           root_=gallery_root,
                           user_content_=user_content,
                           back_=parent_album(index, len(keys)),
                           albums_=child_albums,
                           thumbnails_=thumbnails,
                           list_heights_=heights,
                           thumbnail_padding_=padding,
                           **meta)
    return html


def get_image_page(image_files, image_keys, index):
    if index < 0 or index >= len(image_keys):
        return None
    original = image_keys[index]
    _, meta, *rest = image_files[original]
    return f"{meta['basename']}.html"


def render_image_page(gallery_root, image_files, image_keys, image_index,
                      image_template, relative_path, page_list):
    image_file, meta, content, _ = image_files[image_keys[image_index]]
    user_content = Template(content)
    if "page_title" not in meta.keys():
        meta["page_title"] = meta["title"]
    meta["assets"] = os.path.join(gallery_root, USER_ASSETS)
    html = image_template.render(page_list_=page_list,
                                 root_=gallery_root,
                                 user_content_=user_content,
                                 image_=os.path.join(relative_path, image_file),
                                 previous_=get_image_page(image_files, image_keys, image_index - 1),
                                 next_=get_image_page(image_files, image_keys, image_index + 1),
                                 **meta)
    return html, f"{meta['basename']}.html"


def create_page(page, page_list, destination_directory, filename, template):
    meta, content = page
    user_content = Template(content)
    html = template.render(user_content_=user_content,
                           page_list_=page_list,
                           **meta)
    fn = os.path.join(destination_directory, filename)
    with open(fn, "w") as fid:
        fid.write(html)


def render_pages(pages, destination_directory, template):
    page_list = list()
    render_list = list()
    for basename, page in pages.items():
        fn = f"{basename}.html"
        meta, _ = page
        home_page = meta.get("render_gallery_here", False)
        if home_page:
            fn = "index.html"
        else:
            render_list.append((page, fn))
        page_list.append((meta["title"], fn))

    for content, fn in render_list:
        create_page(content, page_list, destination_directory, fn, template)

    return page_list


def render(album, error_page, pages, output_directory, theme, config):
    env = Environment(
        loader=FileSystemLoader(theme),
        autoescape=select_autoescape(['html', 'xml'])
    )
    album_template = env.get_template("album.html")
    image_template = env.get_template("image.html")
    error_template = env.get_template("error.html")

    page_list = list()
    if len(pages) > 0:
        pages_template = env.get_template("pages.html")
        page_list = render_pages(pages, output_directory, pages_template)

    create_page(error_page, page_list, output_directory, "error.html", error_template)

    keys = tuple(album.keys())
    for index in range(len(keys)):
        album_page = render_album_page(album, keys, index, album_template, page_list, config)
        dst_directory = os.path.join(output_directory, keys[index])
        album_filename = os.path.join(dst_directory, "index.html")
        with open(album_filename, 'w') as fid:
            fid.write(album_page)

        relative, _, image_files, _, _ = album[keys[index]]
        image_keys = tuple(image_files.keys())
        relative_path = os.path.join(relative, GALLERY, IMAGES)
        for k in range(len(image_keys)):
            image_page, filename = render_image_page(gallery_root=relative,
                                                     image_files=image_files,
                                                     image_keys=image_keys,
                                                     image_index=k,
                                                     image_template=image_template,
                                                     relative_path=relative_path,
                                                     page_list=page_list)
            fn = os.path.join(dst_directory, filename)
            with open(fn, "w") as fid:
                fid.write(image_page)
