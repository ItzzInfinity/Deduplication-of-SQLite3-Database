import sqlite3
import os
from pathlib import Path
from collections import defaultdict

# Configuration
WORKSPACE_DIR = Path(__file__).parent
DB_FILES = list(WORKSPACE_DIR.glob("*.db"))
OUTPUT_DB = WORKSPACE_DIR / "UNIQUE.db"

def get_tables(db_path):
    """Get all table names from a database file."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        return tables
    except Exception as e:
        print(f"❌ Error reading {db_path}: {e}")
        return []

def compare_all_tables():
    """Check if all databases have the same tables."""
    print("\n" + "="*60)
    print("STEP 1: Comparing Tables Across All Databases")
    print("="*60)
    
    if not DB_FILES:
        print("❌ No .db files found in the directory!")
        return False
    
    print(f"✓ Found {len(DB_FILES)} database files (excluding UNIQUE.db)\n")
    
    all_tables = {}
    for db_file in DB_FILES:
        if 'UNIQUE.db' in db_file.name:
            continue
        tables = get_tables(db_file)
        all_tables[db_file.name] = set(tables)
        print(f"  {db_file.name}: {len(tables)} tables")
    
    # Compare all tables
    if not all_tables:
        print("❌ No database files found!")
        return False
        
    first_db_tables = set(next(iter(all_tables.values())))
    all_same = all(tables == first_db_tables for tables in all_tables.values())
    
    if all_same:
        print(f"\n✓ All databases have the same {len(first_db_tables)} tables!")
    else:
        print("\n⚠ NOTE: Databases have DIFFERENT tables (this is OK)")
    
    # Check for Song or song table (case-insensitive)
    song_table_exists = any(t.lower() == "song" for t in first_db_tables)
    return song_table_exists

def deduplicate_songs():
    """Extract unique songs from all databases and create UNIQUE.db."""
    print("\n" + "="*60)
    print("STEP 2: Extracting and Deduplicating Songs")
    print("="*60)
    
    # Dictionary to store unique songs by ID
    unique_songs = {}
    song_count_per_db = defaultdict(int)
    
    # Read songs from all databases
    for db_file in DB_FILES:
        if 'UNIQUE.db' in db_file.name:
            continue
            
        try:
            conn = sqlite3.connect(db_file)
            cursor = conn.cursor()
            
            # Try to find Song table (case-insensitive)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            
            # Find the song table (case-insensitive)
            table_name = None
            for t in tables:
                if t.lower() == 'song':
                    table_name = t
                    break
            
            if not table_name:
                conn.close()
                continue
            
            # Get the schema of the Song table
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            column_names = [col[1] for col in columns]
            
            # Read all songs
            cursor.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()
            
            print(f"  {db_file.name}: {len(rows)} songs from '{table_name}' table")
            song_count_per_db[db_file.name] = len(rows)
            
            # Store songs by ID (primary key is 'id')
            for row in rows:
                # Create a dictionary for each row
                song_dict = dict(zip(column_names, row))
                song_id = song_dict.get('id')
                
                if song_id is not None:
                    if song_id not in unique_songs:
                        # Normalize the song dict to have consistent keys
                        normalized = {
                            'id': song_id,
                            'title': song_dict.get('title'),
                            'artistsText': song_dict.get('artistsText') or song_dict.get('artist'),
                            'durationText': song_dict.get('durationText'),
                            'duration': song_dict.get('duration'),
                            'thumbnailUrl': song_dict.get('thumbnailUrl'),
                            'likedAt': song_dict.get('likedAt') or song_dict.get('likedDate'),
                            'totalPlayTimeMs': song_dict.get('totalPlayTimeMs') or song_dict.get('totalPlayTime'),
                            'loudnessBoost': song_dict.get('loudnessBoost'),
                            'blacklisted': song_dict.get('blacklisted', 0),
                            'explicit': song_dict.get('explicit', 0),
                        }
                        unique_songs[song_id] = normalized
            
            conn.close()
            
        except Exception as e:
            print(f"  ❌ Error processing {db_file.name}: {e}")
    
    print(f"\n✓ Total unique songs found: {len(unique_songs)}")
    for db_name, count in sorted(song_count_per_db.items()):
        print(f"  {db_name}: {count} songs")
    
    return unique_songs

def create_unique_db(unique_songs):
    """Create UNIQUE.db with deduplicated songs and URL column."""
    print("\n" + "="*60)
    print("STEP 3: Creating UNIQUE.db with URL Column")
    print("="*60)
    
    # Remove existing UNIQUE.db if it exists
    if OUTPUT_DB.exists():
        OUTPUT_DB.unlink()
        print(f"  Deleted existing {OUTPUT_DB.name}")
    
    try:
        conn = sqlite3.connect(OUTPUT_DB)
        cursor = conn.cursor()
        
        # Manually create the Song table - use the structure from a ViTune database
        create_statement = """
        CREATE TABLE `Song` (
            `id` TEXT NOT NULL, 
            `title` TEXT NOT NULL, 
            `artistsText` TEXT, 
            `durationText` TEXT, 
            `duration` INTEGER,
            `thumbnailUrl` TEXT, 
            `likedAt` INTEGER, 
            `totalPlayTimeMs` INTEGER, 
            loudnessBoost REAL, 
            `blacklisted` INTEGER NOT NULL DEFAULT false, 
            `explicit` INTEGER NOT NULL DEFAULT false,
            `url` TEXT,
            PRIMARY KEY(`id`)
        )
        """
        cursor.execute(create_statement)
        print("  Created Song table with URL column")
        
        # Insert unique songs with generated URLs
        inserted_count = 0
        skipped_count = 0
        
        for song_id, song_dict in unique_songs.items():
            try:
                # Prepare values - use the normalized structure
                id_val = song_dict.get('id')
                title_val = song_dict.get('title')
                artists_val = song_dict.get('artistsText')
                duration_text_val = song_dict.get('durationText')
                duration_val = song_dict.get('duration')
                thumbnail_val = song_dict.get('thumbnailUrl')
                liked_val = song_dict.get('likedAt')
                total_play_val = song_dict.get('totalPlayTimeMs')
                loudness_val = song_dict.get('loudnessBoost')
                blacklisted_val = song_dict.get('blacklisted', 0)
                explicit_val = song_dict.get('explicit', 0)
                url_val = f"https://www.youtube.com/watch?v={song_id}"
                
                # Only insert if we have the required fields
                if id_val and title_val:
                    insert_sql = """
                    INSERT INTO Song 
                    (id, title, artistsText, durationText, duration, thumbnailUrl, likedAt, 
                     totalPlayTimeMs, loudnessBoost, blacklisted, explicit, url) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                    values = [id_val, title_val, artists_val, duration_text_val, duration_val,
                              thumbnail_val, liked_val, total_play_val, loudness_val,
                              blacklisted_val, explicit_val, url_val]
                    
                    cursor.execute(insert_sql, values)
                    inserted_count += 1
                else:
                    skipped_count += 1
                    
            except sqlite3.IntegrityError:
                # Primary key violation - duplicate
                skipped_count += 1
            except Exception as e:
                print(f"  ⚠ Error inserting song ID {song_id}: {e}")
                skipped_count += 1
        
        conn.commit()
        conn.close()
        
        print(f"\n✓ Successfully created {OUTPUT_DB.name}")
        print(f"  Total unique songs extracted: {len(unique_songs)}")
        print(f"  Songs inserted: {inserted_count}")
        if skipped_count > 0:
            print(f"  Songs skipped (duplicates/invalid): {skipped_count}")
        print(f"\n✓ URL column format: https://www.youtube.com/watch?v=<id>")
        
        return True
        
    except Exception as e:
        print(f"❌ Error creating UNIQUE.db: {e}")
        import traceback
        traceback.print_exc()
        return False

def verify_unique_db():
    """Verify the created UNIQUE.db."""
    print("\n" + "="*60)
    print("STEP 4: Verifying UNIQUE.db")
    print("="*60)
    
    try:
        conn = sqlite3.connect(OUTPUT_DB)
        cursor = conn.cursor()
        
        # Get song count
        cursor.execute("SELECT COUNT(*) FROM Song")
        count = cursor.fetchone()[0]
        print(f"✓ Total songs in UNIQUE.db: {count}")
        
        # Show sample
        cursor.execute("SELECT id, title, url FROM Song LIMIT 3")
        samples = cursor.fetchall()
        print(f"\n✓ Sample songs:")
        for song_id, title, url in samples:
            print(f"  ID: {song_id}")
            print(f"  Title: {title}")
            print(f"  URL: {url}")
            print()
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error verifying UNIQUE.db: {e}")

def main():
    """Main execution."""
    print("\n" + "#"*60)
    print("# SQLite Database Deduplication Script")
    print("#"*60)
    print(f"Working directory: {WORKSPACE_DIR}")
    
    # Step 1: Compare tables
    has_song_table = compare_all_tables()
    
    if not has_song_table:
        print("\n❌ No 'Song' table found in the databases!")
        return
    
    # Step 2: Deduplicate songs
    unique_songs = deduplicate_songs()
    
    if not unique_songs:
        print("\n❌ No songs found to process!")
        return
    
    # Step 3: Create UNIQUE.db
    create_unique_db(unique_songs)
    
    # Step 4: Verify
    verify_unique_db()
    
    print("\n" + "#"*60)
    print("# ✓ Process Completed Successfully!")
    print("#"*60)

if __name__ == "__main__":
    main()
