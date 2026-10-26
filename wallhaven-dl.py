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
)

def say_error(message: str, exit_code: int = 1) -> int:
    print(f"wallhaven-dl: error: {message}", file=sys.stderr)
    return exit_code

def say_msg(message: str) -> None:
    print(message)

class FileAlreadyExistsError(Exception):
    pass

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
        "--output-dir",
        type=str,
        default=".",
        help="Directory to save the wallpaper in (Default: current directory)."
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
        
    path = os.path.expanduser(value)
    
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as file:
            api_key = file.read().strip()
            
        if not api_key:
            raise ValueError(f"API key file is empty: {path}")
        
        return api_key
        
    return value

def get_resolution(value: str) -> tuple[int, int]:
    try:
        parts = value.lower().split("x")

        if len(parts) != 2:
            raise ValueError

        w, h = (int(part.strip()) for part in parts)
        
        if w <= 0 or h <= 0:
            raise ValueError
            
        return (w, h)
        
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid resolution '{value}'. "
            "Expected positive WxH dimensions, e.g. 1920x1080."
        )

def get_resolutions(value: str) -> list[tuple[int, int]]:
    items = value.split(",")

    if not all(item.strip() for item in items):
        raise argparse.ArgumentTypeError(
            "Resolutions must be comma-separated without empty entries."
        )

    resolutions = [get_resolution(item.strip()) for item in items]

    if len(resolutions) != len(set(resolutions)):
        raise argparse.ArgumentTypeError(
            "Duplicate resolutions are not allowed."
        )

    return resolutions    

def get_save_path(path, wallpaper_id):
    path = os.path.abspath(os.path.expanduser(path or "."))
    filename = f"wallpaper-{wallpaper_id}.jpg"
    save_path = os.path.join(path, filename)

    if os.path.exists(path) and not os.path.isdir(path):
        raise NotADirectoryError(f"Output path is not a directory: {path}")

    if os.path.exists(save_path):
        raise FileAlreadyExistsError(save_path)
    
    os.makedirs(path, exist_ok=True)
    
    return save_path

def search_wallpaper(
    api,
    query=None,
    atleast=None,
    resolutions=None,
    purities=None,
    sorting=None,
    categories=None,
    order=None,
    top_range=None,
):
    result = api.search(
        q=query,
        categories=categories,
        purities=purities,
        sorting=sorting,
        order=order,
        top_range=top_range,
        atleast=atleast,
        resolutions=resolutions,
    )
    
    wallpapers = result.get("data", [])
    
    if not wallpapers:
        return None
        
    return wallpapers[0]["id"]

def download_wallpaper(api, wallpaper_id, save_path) -> str:
    say_msg(f"Downloading {wallpaper_id}...")
    
    path = api.download_wallpaper(
        wallpaper_id=wallpaper_id,
        file_path=save_path,
    )
    
    if path:
        say_msg(f"Wallpaper saved to {path}")
    
    return path
        
def main() -> int:
    args = parse_args()
    
    try:
        api_key = get_api_key(args.api_key)
        api = WallhavenAPI(api_key=api_key)

        wallpaper_id = search_wallpaper(
            api,
            query=args.query,
            atleast=args.atleast,
            resolutions=args.resolutions,
            purities=args.purities,
            sorting=args.sorting,
            categories=args.categories,
            order=args.order,
            top_range=args.top_range,
        )
        
        if wallpaper_id is None:
            return say_error(
                "No wallpaper found."
            )

        save_path = get_save_path(
            path=args.output_dir,
            wallpaper_id=wallpaper_id,
        )

        download_wallpaper(
            api,
            wallpaper_id,
            save_path,
        )
        
        return 0
    
    except FileAlreadyExistsError as e:
        return say_error(
            f"File already exists: {e}"
        )

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
