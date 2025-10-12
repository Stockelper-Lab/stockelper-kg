"""MongoDB collector for competitor data."""

import pandas as pd
from pymongo import MongoClient

from ..config import MongoDBConfig
from .base import BaseCollector


class MongoDBCollector(BaseCollector):
    """Collector for competitor data from MongoDB."""

    def __init__(self, config: MongoDBConfig):
        """Initialize MongoDB collector.

        Args:
            config: MongoDB configuration
        """
        super().__init__()
        self.config = config

    def collect(self) -> pd.DataFrame:
        """Collect competitor data from MongoDB.

        Returns:
            DataFrame with competitor information
        """
        try:
            client = MongoClient(
                self.config.uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
            )
            db = client[self.config.database]
            collection = db[self.config.collection]

            # Test connection
            client.admin.command("ping")

            documents = collection.find()
            data = list(documents)

            if data:
                competitor_df = pd.DataFrame(data)
                self.logger.info("Converted MongoDB to competitor_df")
                competitor_df = competitor_df.rename(columns={"_id": "stock_code"})

                if "competitors" in competitor_df.columns:
                    competitor_df["compete_code_li"] = competitor_df[
                        "competitors"
                    ].apply(
                        lambda comp_list: (
                            [comp["code"] for comp in comp_list if "code" in comp]
                            if isinstance(comp_list, list)
                            else []
                        )
                    )
                    competitor_df = competitor_df[["stock_code", "compete_code_li"]]
                else:
                    competitor_df = competitor_df[["stock_code"]]
                    competitor_df["compete_code_li"] = [
                        [] for _ in range(len(competitor_df))
                    ]
                return competitor_df
            else:
                self.logger.info("No data in collection")
                return pd.DataFrame(columns=["stock_code", "compete_code_li"])

        except Exception as e:
            self.logger.error(f"Failed to connect to DB: {e}")
            self.logger.info("Using empty competitor DataFrame due to connection failure")
            return pd.DataFrame(columns=["stock_code", "compete_code_li"])
        finally:
            try:
                client.close()
            except Exception:
                pass
