#!/usr/bin/env python3

import os
import sys
import argparse

from wallhavenapi import (
    WallhavenAPI,
    RequestsLimitError,
    ApiKeyError,
    NoWallpaperError,
    UnhandledException,
    Purity,
    Sorting,
    Category,
    Order,
    TopRange,
    Color,
    Type,
)

def say_error(message: str, exit_code: int = 1) -> int:
    print(f"wallhaven-dl: error: {message}", file=sys.stderr)
    return exit_code

def enum_args(parser, name: str, enum_cls, help: str):
    def parse_enum_list(value: str):
        values = [v.strip().lower() for v in value.split(",")]
        
        if not all(values):
            raise argparse.ArgumentTypeError(
                "Values must be comma-separated without empty entries."
            )
            
        parsed = []
        
        for value in values:
            try:
                parsed.append(enum_cls(value))
            except ValueError:
                choices = ", ".join(e.value for e in enum_cls)
                raise argparse.ArgumentTypeError(
                    f"Invalid value '{value}'. Choose from: {choices}"
                )
            
        if len(parsed) != len(set(parsed)):
            raise argparse.ArgumentTypeError(
                "Duplicate values are not allowed."
            )
        
        return parsed
        
    parser.add_argument(
        f"--{name}",
        type=parse_enum_list,
        help=f"{help} (choices: {', '.join(e.value for e in enum_cls)})"
    )

def parse_args():
    parser = argparse.ArgumentParser(
        description="wallhaven-dl - Download a wallpaper from Wallhaven.cc"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="File name to save the wallpaper as (Default: ./wallpaper-ID.jpg). Arguments with trailing '/' create a new directory, if it doesn't exist, and uses the default naming scheme. Arguments without trailing slash become the file name."
    )
    
    parser.add_argument(
        "--api-key",
        type=str,
        help="API key or path to a file containing your API key"
    )
    
    parser.add_argument(
        "--query",
        type=str,
        help="Keyword used to search Wallhaven"
    )
    
    enum_args(
        parser,
        "categories",
        Category,
        "Preferred categories to search in; optional comma-separated list"
    )
    
    enum_args(
        parser,
        "purities",
        Purity,
        "Purities to apply in search; 'nsfw' and 'sketchy' only usable if API key is provided; optional comma-separated list"
    )
    
    parser.add_argument(
        "--sorting",
        type=Sorting,
        default=Sorting.random,
        help=f"Sorting (choices: {', '.join(e.value for e in Sorting)})"
    )
    
    parser.add_argument(
        "--order",
        type=Order,
        default=Order.desc,
        help=f"Result ordering (choices: {', '.join(e.value for e in Order)})"
    )
    
    parser.add_argument(
        "--top-range",
        type=TopRange,
        default=TopRange.one_week,
        help=f"Toplist time range (choices: {', '.join(e.value for e in TopRange)})"
    )
    
    parser.add_argument(
        "--atleast",
        type=get_resolution,
        metavar="WxH",
        help="Minimum wallpaper resolution (e.g. 1920x1080)."
    )
    
    parser.add_argument(
        "--resolutions",
        type=get_resolutions,
        metavar="WxH,WxH,...",
        help="Exact wallpaper resolutions, comma-separated "
             "(e.g. 1920x1080,2560x1440,3840x2160)."
    )
    
    args = parser.parse_args()
    
    if not args.api_key:
        if args.purities and any(p != Purity.sfw for p in args.purities):
            parser.error("Using 'sketchy' or 'nsfw' purities requires --api-key")
        
        if not args.purities:
            args.purities = [Purity.sfw]
    
    for name, enum_cls in {
        "purities": Purity,
        "categories": Category
    }.items():
        values = getattr(args, name)
        if values and len(values) > len(enum_cls):
            parser.error(f"--{name} accepts at most {len(enum_cls)} values.")
            
    return args

def get_api_key(value: str):
    if not value:
        return None
        
    file_path = os.path.expanduser(value)
    
    if os.path.isfile(file_path):
        with open(file_path, "r", encoding="utf-8") as file:
            api_key = file.read().strip()
            
        if not api_key:
            raise ValueError(f"API key file is empty: {file_path}")
        
        return api_key
        
    return value

def get_resolution(value: str):
    try:
        w, h = value.lower().split("x")
        w, h = int(w), int(h)
        
        if w <= 0 or h <= 0:
            raise ValueError
            
        return (w, h)
        
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Resolution must be positive WxH dimensions."
            f"e.g. 1920x1080 (got '{value}')"
        )

def get_resolutions(value: str):
    return [
        get_resolution(item.strip())
        for item in value.split(",")
    ]

def get_save_path(save_path, wallpaper_id):
    default_filename = f"wallpaper-{wallpaper_id}.jpg"
    
    if save_path is None:
        save_path = default_filename
    else:
        save_path = os.path.expanduser(save_path)
        
        if os.path.isdir(save_path) or save_path.endswith(os.sep):
            save_path = os.path.join(save_path, default_filename)
        
    if not os.path.isabs(save_path):
        save_path = os.path.abspath(save_path)
    
    directory = os.path.dirname(save_path)
    filename = os.path.basename(save_path)
    name, extension = os.path.splitext(filename)
    
    if not extension:
        extension = ".jpg"
        filename = f"{name}{extension}"
        save_path = os.path.join(directory, filename)
    
    if os.path.exists(save_path):
        print(f"Warning: {save_path} already exists!")
        default_filename = f"wallpaper-{wallpaper_id}{extension}"
        
        if filename == default_filename:
            print(f"Download aborted.")
            return None
        
        save_path = os.path.join(directory, default_filename)
        
        if os.path.exists(save_path):
            print(f"Warning: {save_path} already exists! Download aborted.")
            return None
    
    os.makedirs(directory, exist_ok=True)
    
    return save_path

def download_wallpaper(api, wallpaper_id, save_path):
    print(f"Downloading: {wallpaper_id}...")
    
    path = api.download_wallpaper(
        wallpaper_id=wallpaper_id,
        file_path=save_path
    )
    
    if path:
        print(f"Wallpaper saved to {path}")
        return path

def search_wallpaper(
    api_key=None,
    query=None,
    save_path=None,
    atleast=None,
    resolutions=None,
    purities=None,
    sorting=None,
    categories=None
):
    api = WallhavenAPI(api_key=api_key)

    result = api.search(
        q=query,
        categories=categories,
        purities=purities,
        sorting=sorting,
        atleast=atleast,
        resolutions=resolutions
    )
    
    wallpapers = result.get("data", [])
    
    if not wallpapers:
        print(f"Error: No wallpapers found.")
        return None
        
    wallpaper_id = wallpapers[0]["id"]
    
    save_path = get_save_path(save_path, wallpaper_id)
    
    if save_path is None:
        return None
        
    return download_wallpaper(api, wallpaper_id, save_path)
        
def main() -> int:
    args = parse_args()
    
    try:
        api_key = get_api_key(args.api_key)

        result = search_wallpaper(
            api_key=api_key or None,
            query=args.query or None,
            save_path=args.output or None,
            atleast=args.atleast or None,
            resolutions=args.resolutions or None,
            purities=args.purities or None,
            sorting=args.sorting or None,
            categories=args.categories or None
        )
        
        if result is None:
            return say_error(
                "No wallpaper downloaded. No results were found, "
                "or the download was canceled because the file exists."
            )
        
        return 0
    
    except ApiKeyError as e:
        return say_error(
            f"{e}. Check your API key and account permissions."
        )
    
    except RequestsLimitError as e:
        return say_error(
            f"{e}. Please wait before making more requests."
        )
    
    except NoWallpaperError as e:
        return say_error(str(e))
    
    except UnhandledException as e:
        return say_error(
            f"Wallhaven API request failed: {e}"
        )
    
    except (ValueError, OSError) as e:
        return say_error(str(e))
        
    except KeyboardInterrupt:
        print("\nwallhaven-dl: download cancelled.", file=sys.stderr)
        return 130

if __name__ == "__main__":
    sys.exit(main())
