"""Scrape un profil Instagram public avec instaloader.

Recupere : bio, nb followers, full_name, categorie, URL photo de profil,
et les N derniers posts (caption + URL photo).

Limites :
- Insta limite environ 50-200 requetes/IP/jour sans login.
- Si bloque, attendre 1-2h ou utiliser un compte dedie (--login).
"""

import time
from dataclasses import dataclass, asdict

try:
    import instaloader
except ImportError:  # pragma: no cover
    instaloader = None  # type: ignore[assignment]


@dataclass
class PostInsta:
    date: str
    caption: str
    url_image: str
    nb_likes: int
    url_post: str


@dataclass
class ProfilInsta:
    handle: str
    nom_complet: str
    bio: str
    site_web: str
    categorie: str
    nb_followers: int
    nb_posts: int
    url_photo_profil: str
    posts: list[PostInsta]


class InstaScraper:
    """Wrapper autour d'instaloader avec rate limiting et gestion d'erreurs."""

    def __init__(self, delai_entre_requetes: float = 30.0):
        if instaloader is None:
            raise RuntimeError("instaloader non installe. Lance : pip install instaloader")
        self.loader = instaloader.Instaloader(
            download_pictures=False,
            download_videos=False,
            download_video_thumbnails=False,
            download_comments=False,
            save_metadata=False,
            quiet=True,
        )
        self.delai = delai_entre_requetes

    def scrape_profil(self, handle: str, max_posts: int = 6) -> ProfilInsta | None:
        try:
            profil = instaloader.Profile.from_username(self.loader.context, handle)
        except instaloader.exceptions.ProfileNotExistsException:
            return None
        except instaloader.exceptions.ConnectionException as e:
            print(f"    [insta-rate-limit] {handle}: {e}")
            return None
        except Exception as e:  # noqa: BLE001
            print(f"    [insta-erreur] {handle}: {e}")
            return None

        posts = []
        if not profil.is_private:
            try:
                for i, post in enumerate(profil.get_posts()):
                    if i >= max_posts:
                        break
                    posts.append(
                        PostInsta(
                            date=post.date_utc.isoformat(),
                            caption=(post.caption or "")[:500],
                            url_image=post.url,
                            nb_likes=post.likes,
                            url_post=f"https://www.instagram.com/p/{post.shortcode}/",
                        )
                    )
                    time.sleep(2)
            except Exception as e:  # noqa: BLE001
                print(f"    [insta-posts-erreur] {handle}: {e}")

        time.sleep(self.delai)
        return ProfilInsta(
            handle=handle,
            nom_complet=profil.full_name or "",
            bio=profil.biography or "",
            site_web=profil.external_url or "",
            categorie=profil.business_category_name or "",
            nb_followers=profil.followers,
            nb_posts=profil.mediacount,
            url_photo_profil=profil.profile_pic_url,
            posts=posts,
        )


def profil_to_dict(profil: ProfilInsta) -> dict:
    return {
        **{k: v for k, v in asdict(profil).items() if k != "posts"},
        "posts": [asdict(p) for p in profil.posts],
    }


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python insta_scraper.py <handle>")
        sys.exit(1)
    scraper = InstaScraper(delai_entre_requetes=5.0)
    profil = scraper.scrape_profil(sys.argv[1])
    if profil:
        print(json.dumps(profil_to_dict(profil), indent=2, ensure_ascii=False))
    else:
        print("Profil non trouve ou bloque")
